"""Entry point Streamlit cho prototype RIKAI. Chạy: streamlit run app.py"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from ui.chat_app import run

if __name__ == "__main__":
    run()
else:
    run()


# & "C:\Program Files\Python311\python.exe" -m pip install -r requirements.txt

# & "C:\Program Files\Python311\python.exe" -m streamlit run app.py


# hãy đọc và phân tích các tệp đó và gửi các hearing sheet đến các partner @VendorB và nuoc_ngot.pdf là file mô tả nội dung còn hearing_sheet_question là nơi chứa các vấn đề càn partner trả lời  