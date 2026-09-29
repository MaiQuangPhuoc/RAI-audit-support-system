from ingestion.xlsx_extractor import _group_rows_into_blocks


def test_repeated_header_row_is_table_not_text():
    rows = [
        [(1, '記号'), (2, '記号'), (3, '回答基準'), (4, '回答基準'), (5, '回答基準')],
        [(1, '〇'), (2, '〇'), (3, '実施している'), (4, '実施している'), (5, '実施している')],
    ]

    blocks = _group_rows_into_blocks(rows)

    assert blocks[0][0] == 'table'
    assert len(blocks) == 1


def test_single_cell_text_row_stays_text():
    rows = [
        [(1, 'ご案内')],
        [(1, '記号'), (2, '記号'), (3, '回答基準'), (4, '回答基準')],
    ]

    blocks = _group_rows_into_blocks(rows)

    assert blocks[0][0] == 'text'
    assert blocks[1][0] == 'table'
