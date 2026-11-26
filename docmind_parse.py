"""直接调用阿里云 DocMind 解析文档。

安装依赖：
    pip install alibabacloud_docmind_api20220711 alibabacloud_tea_openapi \
        alibabacloud_tea_util python-dotenv

在项目根目录 .env 中配置：
    ALIBABA_CLOUD_ACCESS_KEY_ID=...
    ALIBABA_CLOUD_ACCESS_KEY_SECRET=...

不带参数时，默认解析规程 PDF，并写入 data/docmind/cjj-181-2012。
也可显式指定：
    python docmind_parse.py "docs/CJJ 181-2012 城镇排水管道检测与评估技术规程.pdf" \
        --output-dir "data/docmind/cjj-181-2012"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from alibabacloud_docmind_api20220711 import models as docmind_models
from alibabacloud_docmind_api20220711.client import Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models
from dotenv import load_dotenv


ENDPOINT = "docmind-api.cn-hangzhou.aliyuncs.com"
POLL_INTERVAL_SECONDS = 10
MAX_WAIT_SECONDS = 120 * 60
LAYOUT_PAGE_SIZE = 300


def _plain(value: Any) -> Any:
    """Convert an Alibaba Tea model response to JSON-compatible values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    for method_name in ("to_map", "toMap"):
        method = getattr(value, method_name, None)
        if callable(method):
            return _plain(method())
    if hasattr(value, "__dict__"):
        return {
            key: _plain(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    return str(value)


def _field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _markdown_url(value: Any) -> str | None:
    """Find the Markdown outputFileUrl returned by DocMind."""
    if isinstance(value, dict):
        output_type = str(
            _field(value, "outputType", "output_type", "OutputType", default="")
        ).lower()
        output_url = _field(value, "outputFileUrl", "output_file_url", "OutputFileUrl")
        if output_type == "markdown" and isinstance(output_url, str):
            return output_url
        for item in value.values():
            found = _markdown_url(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _markdown_url(item)
            if found:
                return found
    return None


def _client() -> Client:
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
    access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    if not access_key_id or not access_key_secret:
        raise RuntimeError(
            "请在项目根目录 .env 中配置 ALIBABA_CLOUD_ACCESS_KEY_ID "
            "和 ALIBABA_CLOUD_ACCESS_KEY_SECRET。"
        )
    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    config.endpoint = ENDPOINT
    config.connect_timeout = 60_000
    config.read_timeout = 60_000
    return Client(config)


def _submit(client: Client, source: Path, *, vlm: bool, formula: bool) -> str:
    with source.open("rb") as stream:
        request = docmind_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=stream,
            file_name=source.name,
            formula_enhancement=formula,
            llm_enhancement=vlm,
            output_format=["markdown", "visualLayoutInfo"],
        )
        if vlm:
            request.enhancement_mode = "VLM"
        response = client.submit_doc_parser_job_advance(
            request, util_models.RuntimeOptions()
        )
    body = response.body
    data = _field(body, "data", "Data", default={})
    task_id = _field(data, "id", "Id")
    if not task_id:
        raise RuntimeError(
            f"DocMind 未返回任务 ID：{json.dumps(_plain(body), ensure_ascii=False)}"
        )
    return str(task_id)


def _wait_for_completion(client: Client, task_id: str) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        response = client.query_doc_parser_status(
            docmind_models.QueryDocParserStatusRequest(id=task_id)
        )
        status_body = _plain(response.body)
        data = _field(response.body, "data", "Data", default={})
        status = str(_field(data, "status", "Status", default="")).lower()
        processing = _field(data, "processing", "Processing", default=None)
        print(f"DocMind status={status or 'unknown'} processing={processing}", flush=True)
        if status == "success":
            return status_body
        if status in {"fail", "failed", "failure"}:
            raise RuntimeError(
                f"DocMind 解析失败：{json.dumps(status_body, ensure_ascii=False)}"
            )
        if time.monotonic() - started >= MAX_WAIT_SECONDS:
            raise TimeoutError(f"DocMind 任务 {task_id} 等待超过 120 分钟。")
        time.sleep(POLL_INTERVAL_SECONDS)


def _get_layouts(client: Client, task_id: str) -> dict[str, Any]:
    layouts: list[Any] = []
    offset = 0
    request_id: str | None = None
    while True:
        response = client.get_doc_parser_result(
            docmind_models.GetDocParserResultRequest(
                id=task_id,
                layout_num=offset,
                layout_step_size=LAYOUT_PAGE_SIZE,
            )
        )
        page = _plain(response.body)
        request_id = _field(
            response.body, "request_id", "requestId", "RequestId", default=request_id
        )
        data = _field(response.body, "data", "Data", default={})
        batch = _field(data, "layouts", "Layouts", default=[])
        if not isinstance(batch, list):
            raise RuntimeError(
                f"DocMind layouts 不是数组：{json.dumps(page, ensure_ascii=False)}"
            )
        layouts.extend(batch)
        if len(batch) < LAYOUT_PAGE_SIZE:
            break
        offset += len(batch)
    return {"RequestId": request_id, "Data": {"layouts": layouts}}


def parse_document(source: Path, output_dir: Path, *, vlm: bool, formula: bool) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"输入文件不存在：{source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = _client()
    task_id = _submit(client, source, vlm=vlm, formula=formula)
    task_file = output_dir / "task.json"
    task_file.write_text(
        json.dumps({"id": task_id, "source": str(source)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    status_body = _wait_for_completion(client, task_id)
    task_file.write_text(
        json.dumps(
            {"id": task_id, "source": str(source), "status_response": status_body},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _get_layouts(client, task_id)
    (output_dir / "document.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_url = _markdown_url(status_body)
    if markdown_url is None:
        raise RuntimeError(
            "任务成功，但 DocMind 状态响应中未找到 Markdown 文件地址。"
            "已保留 task.json 和 document.json。"
        )
    with urlopen(markdown_url, timeout=60) as response:
        (output_dir / "document.md").write_bytes(response.read())
    print(f"已保存 DocMind 原始结果：{output_dir / 'document.json'}")
    print(f"已保存 DocMind Markdown：{output_dir / 'document.md'}")


DEFAULT_INPUT = Path("docs/CJJ 181-2012 城镇排水管道检测与评估技术规程.pdf")
DEFAULT_OUTPUT_DIR = Path("data/docmind/cjj-181-2012")


def main() -> None:
    parser = argparse.ArgumentParser(description="直接使用阿里云 DocMind 解析 PDF/文档")
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"待解析的本地 PDF 或其他受支持文件（默认：{DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"结果输出目录（默认：{DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument("--no-vlm", action="store_true", help="关闭 VLM 增强")
    parser.add_argument(
        "--no-formula-enhancement", action="store_true", help="关闭公式识别增强"
    )
    args = parser.parse_args()
    try:
        parse_document(
            args.input,
            args.output_dir,
            vlm=not args.no_vlm,
            formula=not args.no_formula_enhancement,
        )
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
