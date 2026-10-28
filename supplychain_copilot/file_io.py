"""File parsing and CSV serialization shared by the UI and tests."""

import csv
import io
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException
from xlrd.biffh import XLRDError

MAX_FILE_BYTES = 20 * 1024 * 1024


def read_inventory_file(name: str, content: bytes) -> pd.DataFrame:
    if not content:
        raise ValueError("文件为空。")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("文件不能超过 20 MB。")
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("gb18030")
        header = next(csv.reader(io.StringIO(text)), [])
        if len(header) != len(set(header)):
            raise ValueError("列名不能重复。")
        return pd.read_csv(io.StringIO(text), dtype={"sku": "string"}, keep_default_na=False)
    if suffix in {".xlsx", ".xls"}:
        engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
        try:
            header_frame = pd.read_excel(io.BytesIO(content), engine=engine, header=None, nrows=1)
            header = header_frame.iloc[0].tolist() if len(header_frame) else []
            if len(header) != len(set(header)):
                raise ValueError("列名不能重复。")
            return pd.read_excel(io.BytesIO(content), engine=engine,
                                 dtype={"sku": "string"}, keep_default_na=False)
        except (BadZipFile, XLRDError, InvalidFileException, OSError, ValueError, KeyError) as exc:
            raise ValueError(f"Excel 文件无法读取：{exc}") from exc
    raise ValueError("仅支持 .csv、.xlsx 和 .xls 文件。")


def export_inventory_csv(result: pd.DataFrame) -> bytes:
    """Export exactly the filtered result, with UTF-8 BOM for Excel."""
    return result.to_csv(index=False, na_rep="").encode("utf-8-sig")
