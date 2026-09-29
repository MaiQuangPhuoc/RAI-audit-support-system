"""
LLMClient hỗ trợ groq / openai / openrouter / anthropic, bật/tắt bằng cách đổi
api_provider trong .env, không cần sửa code.

Dựa trên llm.py do Auditor cung cấp — chỉ chỉnh lại import (configs.py giờ
nằm ở gốc project thay vì src/configs.py) và bỏ đoạn sys.path.append không
còn cần thiết. Toàn bộ logic gọi LLM, retry, bind tools, structured output
giữ nguyên như bản gốc.
"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import logging
from typing import List, Optional, Union

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import BaseTool
from pydantic import BaseModel

from configs import env_config

logger = logging.getLogger(__name__)






import logging
from typing import List, Optional, Union

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import BaseTool
from pydantic import BaseModel

from configs import env_config

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client hỗ trợ groq / openai / openrouter / anthropic, bật/tắt bằng cách
    đổi api_provider trong .env, không cần sửa code."""

    def __init__(self, model: str, api_provider: str = None):
        self.model = model
        self.api_provider = api_provider or env_config.api_provider
        self._llm = self._initialize_llm()

    def _initialize_llm(self):
        provider = self.api_provider

        if provider == "groq":
            from langchain_groq import ChatGroq
            if not env_config.groq_api_key:
                raise ValueError("Thiếu GROQ_API_KEY trong .env")
            return ChatGroq(model=self.model, groq_api_key=env_config.groq_api_key)

        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            if not env_config.openai_api_key:
                raise ValueError("Thiếu OPENAI_API_KEY trong .env")
            return ChatOpenAI(model=self.model, api_key=env_config.openai_api_key)

        elif provider == "openrouter":
            from langchain_openai import ChatOpenAI
            if not env_config.openrouter_api_key:
                raise ValueError("Thiếu OPENROUTER_API_KEY trong .env")
            return ChatOpenAI(
                model=self.model,
                api_key=env_config.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
            )

        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            if not env_config.anthropic_api_key:
                raise ValueError("Thiếu ANTHROPIC_API_KEY trong .env")
            return ChatAnthropic(
                model=self.model,
                api_key=env_config.anthropic_api_key,
                max_tokens=4096,
            )

        else:
            raise ValueError(f"api_provider không hỗ trợ: {provider}")

    def _configure_llm(self, max_tokens, temperature, llm_tools, output_model, structured_method=None):
        llm = self._llm.bind(max_tokens=max_tokens, temperature=temperature)
        if llm_tools:
            llm = llm.bind_tools(llm_tools)
        if output_model:
            kwargs = {"method": structured_method} if structured_method else {}
            llm = llm.with_structured_output(output_model, **kwargs)
        return llm

    def invoke_with_retries(self, prompt: ChatPromptTemplate, max_tokens=1024,
                             temperature=1, llm_tools: List[BaseTool] = None,
                             output_model: Optional[BaseModel] = None, num_retries=1,
                             structured_method: Optional[str] = None):
        llm_tools = llm_tools or []
        llm = self._configure_llm(max_tokens, temperature, llm_tools, output_model, structured_method)
        for attempt in range(num_retries):
            try:
                chain = prompt | llm
                response = chain.invoke(input={})
                logger.info(f"LLM invocation successful on attempt {attempt + 1}")
                return response
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt == num_retries - 1:
                    raise
                logger.info(f"Retrying... {attempt + 2}/{num_retries}")

    async def ainvoke_with_retries(self, prompt: Union[ChatPromptTemplate, List[BaseMessage]],
                                    max_tokens=1024, temperature=1,
                                    llm_tools: List[BaseTool] = None,
                                    output_model: Optional[BaseModel] = None, num_retries=1):
        llm_tools = llm_tools or []
        llm = self._configure_llm(max_tokens, temperature, llm_tools, output_model)
        for attempt in range(num_retries):
            try:
                if isinstance(prompt, list):
                    return await llm.ainvoke(prompt)
                chain = prompt | llm
                return await chain.ainvoke(input={})
            except Exception as e:
                logger.error(f"Lỗi ở lần thử thứ {attempt + 1}: {e}")
                if attempt == num_retries - 1:
                    raise
                logger.info(f"Đang thử lại... ({attempt + 2}/{num_retries})")


# Global client — comment dòng dưới nếu không muốn auto-init lúc import
try:
    llm_client = LLMClient(model=env_config.model, api_provider=env_config.api_provider)
except Exception as e:
    logger.error(f"Failed to initialize global LLM client: {e}")
    llm_client = None


# ---------------------------------------------------------------------------
# Helper cho các agent (hearing_sheet_agent, analysis_agent, report_agent):
# tất cả đều gọi LLM thông qua invoke_with_retries của llm_client ở trên,
# không gọi thẳng OpenAI/Groq SDK ở nơi khác trong project.
# ---------------------------------------------------------------------------

def _escape_braces(text: str) -> str:
    """
    ChatPromptTemplate coi { } là placeholder biến. Prompt của RIKAI có nhiều
    ví dụ JSON chứa { }, nên cần escape thành {{ }} trước khi đưa vào template
    để tránh lỗi 'input variable không được cung cấp'.
    """
    return text.replace("{", "{{").replace("}", "}}")


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2,
             max_tokens: int = 1500, num_retries: int = 2) -> str:
    """Gọi LLM với 1 system prompt + 1 user prompt, trả về text thuần."""
    if llm_client is None:
        raise RuntimeError(
            "LLM client chưa khởi tạo được. Kiểm tra .env: api_provider đang chọn là "
            f"'{env_config.api_provider}', cần có API key tương ứng "
            "(OPENAI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY)."
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", _escape_braces(system_prompt)),
        ("human", _escape_braces(user_prompt)),
    ])
    response = llm_client.invoke_with_retries(
        prompt, max_tokens=max_tokens, temperature=temperature, num_retries=num_retries
    )
    return response.content if hasattr(response, "content") else str(response)


def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.1,
                   max_tokens: int = 2000, num_retries: int = 2) -> dict:
    """Gọi LLM và parse kết quả JSON. Raise lỗi rõ ràng nếu model trả JSON không hợp lệ."""
    import json

    raw = call_llm(system_prompt, user_prompt, temperature=temperature,
                    max_tokens=max_tokens, num_retries=num_retries)

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM trả về JSON không hợp lệ, không thể parse. Nội dung thô:\n{raw}"
        ) from e


def call_llm_structured(system_prompt: str, user_prompt: str, schema, temperature: float = 0.1,
                         max_tokens: int = 3000, num_retries: int = 2):
    """
    Gọi LLM và ép trả về đúng theo `schema` (1 class Pydantic BaseModel), dùng
    tính năng structured output (output_model) có sẵn của LLMClient. Trả về
    thẳng 1 instance của schema — không cần tự parse JSON.

    Một số model (đặc biệt model open-weight qua Groq/OpenRouter, VD:
    gpt-oss) đôi khi KHÔNG tuân thủ đúng tool-calling — tự bịa tên tool khác
    với tool đã đăng ký, gây lỗi "tool call validation failed" / "was not in
    request.tools" từ phía provider. Khi gặp đúng lỗi này, tự động thử lại 1
    lần bằng method="json_mode" (không dùng tool-calling, ép model trả JSON
    thuần) — cách này ổn định hơn với các model chưa luyện kỹ tool-calling.
    """
    if llm_client is None:
        raise RuntimeError(
            "LLM client chưa khởi tạo được. Kiểm tra .env: api_provider đang chọn là "
            f"'{env_config.api_provider}', cần có API key tương ứng."
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", _escape_braces(system_prompt)),
        ("human", _escape_braces(user_prompt)),
    ])
    try:
        return llm_client.invoke_with_retries(
            prompt, max_tokens=max_tokens, temperature=temperature,
            output_model=schema, num_retries=num_retries,
        )
    except Exception as e:
        msg = str(e).lower()
        tool_call_issue = (
            "tool call validation failed" in msg
            or "was not in request.tools" in msg
            or "tool_use_failed" in msg
        )
        if not tool_call_issue:
            raise
        logger.warning(
            f"Structured output qua tool-calling thất bại (model có thể không tuân thủ "
            f"tool-calling đúng chuẩn): {str(e)[:200]}... Thử lại bằng method='json_mode'."
        )
        # response_format=json_object (bên dưới của method="json_mode") của nhiều provider
        # (VD: Groq) BẮT BUỘC message phải chứa chữ "json" — prompt tiếng Việt không có
        # sẵn chữ này nên phải thêm dòng hướng dẫn rõ ràng trước khi thử lại.
        json_mode_prompt = ChatPromptTemplate.from_messages([
            ("system", _escape_braces(system_prompt)),
            ("human", _escape_braces(user_prompt) + "\n\nTrả lời CHỈ bằng một object json hợp lệ, không thêm chữ nào khác."),
        ])
        return llm_client.invoke_with_retries(
            json_mode_prompt, max_tokens=max_tokens, temperature=temperature,
            output_model=schema, num_retries=num_retries, structured_method="json_mode",
        )


# ---------------------------------------------------------------------------
# Test nhanh: chạy trực tiếp file này để kiểm tra provider/model/API key
# trong .env có hoạt động không, không cần khởi động cả Streamlit.
#   python core/llm.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("-- RIKAI LLM test --")
    print(f"provider : {env_config.api_provider}")
    print(f"model    : {env_config.model}")

    query   = """Bạn là một Data Extraction Agent trong hệ thống RIKAI. Nhiệm vụ duy nhất của bạn là đọc nội dung Markdown được cung cấp và trích xuất các câu hỏi cùng các trường/cột tương ứng. KHÔNG phân tích nội dung câu hỏi. KHÔNG tóm tắt. KHÔNG viết lại câu hỏi. KHÔNG dịch. KHÔNG suy luận thêm thông tin. KHÔNG tự tạo dữ liệu không tồn tại trong input. ================================================== MỤC TIÊU ================================================== Input có thể chứa: - Markdown table - text - nhiều bảng - heading - các câu hỏi - các cột cha / cột con - các ô có giá trị hoặc để trống Bạn phải xác định cấu trúc thực tế xuất hiện trong input. Mỗi câu hỏi phải được trả về thành một QuestionItem. Trong QuestionItem: question = nội dung câu hỏi đúng theo input. fields = toàn bộ các trường/cột liên quan đến câu hỏi đó. Mỗi field phải có: name = tên trường/cột đúng theo input. value = giá trị thực tế của ô tương ứng. parent_column = tên cột cha nếu trường này nằm dưới một cột cha. Nếu không có cột cha thì để "". ================================================== QUY TẮC QUAN TRỌNG ================================================== 1. GIỮ NGUYÊN DỮ LIỆU Không được thay đổi nội dung câu hỏi. Không được tự sửa chính tả. Không được dịch tiếng Nhật sang tiếng Việt. Không được rút gọn câu hỏi. -------------------------------------------------- 2. Ô TRỐNG Nếu một trường/cột tồn tại nhưng ô tương ứng không có dữ liệu: value = "" Ví dụ: | 質問 | 回答 | コメント | |---|---|---| | 質問A | Yes | | thì phải giữ: 回答 = "Yes" コメント = "" Không được bỏ cột コメント. -------------------------------------------------- 3. PHẢI GIỮ CỘT Nếu một cột xuất hiện trong bảng thì phải giữ lại, kể cả khi toàn bộ giá trị của cột đó đang trống. Không được bỏ cột chỉ vì nó không có dữ liệu. -------------------------------------------------- 4. CỘT CHA Nếu input thể hiện cấu trúc cột cha / cột con, phải giữ quan hệ này. Ví dụ: | 基本情報 | 基本情報 | セキュリティ | |---|---|---| | 会社名 | 所在地 | 認証取得 | thì các field phải giữ parent_column tương ứng nếu cấu trúc input thể hiện rõ quan hệ đó. Không được tự suy đoán quan hệ cha-con nếu input không thể hiện. -------------------------------------------------- 5. KHÔNG GOM CÂU HỎI Mỗi câu hỏi trong input phải là một QuestionItem riêng. Không được gộp nhiều câu hỏi thành một câu hỏi. Ví dụ: Q1 Q2 Q3 phải trả về: questions = [ Q1, Q2, Q3 ] -------------------------------------------------- 6. KHÔNG BỎ QUA CÂU HỎI Nếu một dòng chứa một câu hỏi hợp lệ, phải giữ dòng đó. Kể cả khi các trường khác của dòng đều trống. -------------------------------------------------- 7. KHÔNG INVENT Nếu không có thông tin trong input: - không tự tạo giá trị - không tự tạo tên cột - không tự tạo câu hỏi - không tự tạo parent_column Trường không xác định được phải để "". -------------------------------------------------- 8. GIỮ THỨ TỰ Giữ nguyên thứ tự câu hỏi theo input. Giữ nguyên thứ tự các field theo cấu trúc input. -------------------------------------------------- 9. CHỈ TRẢ VỀ STRUCTURED OUTPUT Kết quả phải tuân thủ QuestionExtractionResult. Không thêm explanation bên ngoài schema. ================================================== QUY TRÌNH SUY LUẬN NỘI BỘ ================================================== Trước khi trả kết quả, thực hiện nội bộ: STEP 1 - OBSERVE Đọc toàn bộ input. STEP 2 - IDENTIFY Xác định các bảng, header, câu hỏi và các field. STEP 3 - MAP Map từng giá trị vào đúng field của câu hỏi tương ứng. STEP 4 - VERIFY Kiểm tra: - có bỏ câu hỏi nào không - có bỏ cột nào không - ô trống có được giữ thành "" không - parent_column có được giữ không - có tự tạo thông tin không STEP 5 - OUTPUT Trả về đúng QuestionExtractionResult. Không hiển thị quá trình suy luận nội bộ. query : Hãy đọc toàn bộ nội dung Markdown dưới đây và trích xuất các câu hỏi theo đúng cấu trúc được yêu cầu. QUY TẮC: - Chỉ trích xuất thông tin có trong input. - Không tự suy luận hoặc bổ sung thông tin. - Không dịch nội dung. - Không viết lại câu hỏi. - Giữ nguyên thứ tự xuất hiện. - Mỗi câu hỏi là một QuestionItem. - Giữ lại toàn bộ field/column liên quan đến câu hỏi. - Nếu field có trong bảng nhưng không có giá trị, value phải là "". - Nếu có quan hệ cột cha/cột con được thể hiện rõ trong bảng, ghi vào parent_column. - Không được bỏ qua column chỉ vì column đó đang trống. MARKDOWN INPUT: ---------------- ## Sheet: ③チェックリスト | No | 分類 | チェック内容 | チェック項目 | 回答（全て必須） | 調達先コメント（△、✖、－の場合は必須） | 確認要否 （弊社） | 面談要望/資料提出依頼事項 | 是正有無 （弊社） | 是正依頼事項（弊社） | 是正依頼回答（質問事項があった場合） | 結果区分 （弊社） | コメント（弊社） | | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | | 1 | ガバナンスの整備 | 貴社では、情報セキュリティ推進活動を担当する部署・責任者（役員を含む）および関係従業員を明確に定め、責任および権限を割り当てたうえで、規程や体制図等により組織内へ周知していますか。 | 1-① 責任部署および責任者が明確化されているか |  |  |  |  |  |  |  |  |  | | 1 | ガバナンスの整備 | 貴社では、情報セキュリティ推進活動を担当する部署・責任者（役員を含む）および関係従業員を明確に定め、責任および権限を割り当てたうえで、規程や体制図等により組織内へ周知していますか。 | 1-② 役割および権限が定義されているか |  |  |  |  |  |  |  |  |  | | 1 | ガバナンスの整備 | 貴社では、情報セキュリティ推進活動を担当する部署・責任者（役員を含む）および関係従業員を明確に定め、責任および権限を割り当てたうえで、規程や体制図等により組織内へ周知していますか。 | 1-③ 関連する規程・体制図が整備され、周知されているか |  |  |  |  |  |  |  |  |  | | 1 | ガバナンスの整備 | 貴社では、情報セキュリティ推進活動を担当する部署・責任者（役員を含む）および関係従業員を明確に定め、責任および権限を割り当てたうえで、規程や体制図等により組織内へ周知していますか。 | 1-④ 実効性（実際に機能しているか）が確認されているか |  |  |  |  |  |  |  |  |  | | 1 | ガバナンスの整備 | 貴社では、情報セキュリティ推進活動を担当する部署・責任者（役員を含む）および関係従業員を明確に定め、責任および権限を割り当てたうえで、規程や体制図等により組織内へ周知していますか。 | 1-⑤ 定期的な見直しや改善が実施されているか |  |  |  |  |  |  |  |  |  | | 2 | ガバナンスの整備 | 貴社では、守秘義務に関するルールを策定し、役員および従業員に対して適切に周知・教育を行い、その遵守を徹底していますか。 | 2-① 守秘義務に関するルールが整備されているか |  |  |  |  |  |  |  |  |  | | 2 | ガバナンスの整備 | 貴社では、守秘義務に関するルールを策定し、役員および従業員に対して適切に周知・教育を行い、その遵守を徹底していますか。 | 2-② 対象者（役員・従業員）へ周知が徹底されているか |  |  |  |  |  |  |  |  |  | | 2 | ガバナンスの整備 | 貴社では、守秘義務に関するルールを策定し、役員および従業員に対して適切に周知・教育を行い、その遵守を徹底していますか。 | 2-③ 教育（定期研修等）が実施されているか |  |  |  |  |  |  |  |  |  | | 2 | ガバナンスの整備 | 貴社では、守秘義務に関するルールを策定し、役員および従業員に対して適切に周知・教育を行い、その遵守を徹底していますか。 | 2-④ 遵守状況の確認方法が定められ、違反時の対応体制が整備されているか |  |  |  |  |  |  |  |  |  | | 2 | ガバナンスの整備 | 貴社では、守秘義務に関するルールを策定し、役員および従業員に対して適切に周知・教育を行い、その遵守を徹底していますか。 | 2-⑤ 定期的な見直しおよび改善が実施されているか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-①方針が策定されているか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-②方針の内容が明確であるか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-③役員および従業員への周知方法が確立され、適切に浸透しているか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-④教育・研修が実施されているか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-⑤遵守状況の確認が行われているか |  |  |  |  |  |  |  |  |  | | 3 | ガバナンスの整備 | 貴社では、自社の情報セキュリティに関する対応方針を策定し、役員および従業員に対して適切に周知していますか。 | 3-⑥定期的な見直しが実施されているか |  |  |  |  |  |  |  |  |  | | 4 | 取引先管理 | 貴社では、サードパーティの役割を特定し自組織のビジネスにおける重要度に応じて管理するとともに、重要なサードパーティに対してはセキュリティ対策状況の評価を実施していますか。 | 4-①サードパーティの特定および重要度分類が行われているか |  |  |  |  |  |  |  |  |  | | 4 | 取引先管理 | 貴社では、サードパーティの役割を特定し自組織のビジネスにおける重要度に応じて管理するとともに、重要なサードパーティに対してはセキュリティ対策状況の評価を実施していますか。 | 4-②重要な委託先に対するセキュリティ評価が実施されているか |  |  |  |  |  |  |  |  |  | | 4 | 取引先管理 | 貴社では、サードパーティの役割を特定し自組織のビジネスにおける重要度に応じて管理するとともに、重要なサードパーティに対してはセキュリティ対策状況の評価を実施していますか。 | 4-③評価結果が適切に管理され、必要に応じた改善対応が行われているか |  |  |  |  |  |  |  |  |  | | 4 | 取引先管理 | 貴社では、サードパーティの役割を特定し自組織のビジネスにおける重要度に応じて管理するとともに、重要なサードパーティに対してはセキュリティ対策状況の評価を実施していますか。 | 4-④サードパーティ管理内容について定期的な見直し・更新が行われているか |  |  |  |  |  |  |  |  |  |"""
    # query = "Hà Nội là thủ đô của Việt Nam, đúng hay sai? Trả lời ngắn gọn."
    # print(f"\nQuery: {query}")
    try:
        answer = call_llm(
            system_prompt="Bạn là trợ lý trả lời ngắn gọn, chính xác.",
            user_prompt=query,
            temperature=0,
        )
        print(f"Trả lời: {answer}")
    except Exception as e:
        print(f"Lỗi khi gọi LLM: {e}")







# ---------------------------------------------------------------------------
# Test nhanh: chạy trực tiếp file này để kiểm tra provider/model/API key
# trong .env có hoạt động không, không cần khởi động cả Streamlit.
#   python core/llm.py
# ---------------------------------------------------------------------------
# if __name__ == "__main__":
#     print("-- RIKAI LLM test --")
#     print(f"provider : {env_config.api_provider}")
#     print(f"model    : {env_config.model}")

#     query = "Hà Nội là thủ đô của Việt Nam, đúng hay sai? Trả lời ngắn gọn."
#     print(f"\nQuery: {query}")
#     try:
#         answer = call_llm(
#             system_prompt="Bạn là trợ lý trả lời ngắn gọn, chính xác.",
#             user_prompt=query,
#             temperature=0,
#         )
#         print(f"Trả lời: {answer}")
#     except Exception as e:
#         print(f"Lỗi khi gọi LLM: {e}")