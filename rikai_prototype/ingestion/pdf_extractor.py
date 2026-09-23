import pdfplumber

def extract_text(file_path: str) -> str:
    pages_text = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_content = [f"[Trang {page_num}]"]
            tables = page.find_tables()

            # Extract table
            for table in tables:
                for row in table.extract():
                    cells = ["" if cell is None else cell.strip() for cell in row]
                    page_content.append(" | ".join(cells))

            # Extract text ngoài table và giữ format dòng
            if tables:
                table_bboxes = [table.bbox for table in tables]
                words = page.extract_words()
                outside_words = []

                for word in words:
                    x, y = word["x0"], word["top"]

                    in_table = any(
                        x0 <= x <= x1 and y0 <= y <= y1
                        for x0, y0, x1, y1 in table_bboxes
                    )

                    if not in_table:
                        outside_words.append(word)

                lines = []
                tolerance = 3

                for word in outside_words:
                    for line in lines:
                        if abs(word["top"] - line["top"]) <= tolerance:
                            line["words"].append(word)
                            break
                    else:
                        lines.append({"top": word["top"], "words": [word]})

                lines.sort(key=lambda x: x["top"])

                for line in lines:
                    line["words"].sort(key=lambda x: x["x0"])
                    page_content.append(
                        " ".join(w["text"] for w in line["words"])
                    )

            else:
                text = page.extract_text() or ""
                if text.strip():
                    page_content.append(text.strip())

            pages_text.append("\n".join(page_content))

    return "\n\n".join(pages_text)

# if __name__ == "__main__":
#     input_path = r"D:\PHUOC\RAI_LLM\rikai_prototype2\rikai_prototype\data\input\data_llm2.pdf"

#     print(extract_text(input_path))
