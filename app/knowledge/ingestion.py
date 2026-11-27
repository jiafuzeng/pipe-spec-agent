"""Shared preview and index transforms for spec 006."""

import hashlib
import json
import os
import re
import threading

from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import NodeRelationship, TransformComponent
from llama_index.core.node_parser import (
    HierarchicalNodeParser,
    MarkdownNodeParser,
    SemanticDoubleMergingSplitterNodeParser,
    SemanticSplitterNodeParser,
    SentenceSplitter,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)

from app.knowledge.source import pages_from_markdown, sections

PROFILES = {"ollama:bge-m3": "local", "dashscope:text-embedding-v2": "cloud"}
CLAUSE = re.compile(r"(?m)^[#>\s]*(?:续)?((?:表\s*)?\d+\.\d+\.\d+(?:-\d+)?)\b")


def clause_of(text):
    found = CLAUSE.search(text)
    return found.group(1).replace(" ", "") if found else None


def model(profile):
    if profile == "ollama:bge-m3":
        from llama_index.embeddings.ollama import OllamaEmbedding

        return OllamaEmbedding(
            model_name="bge-m3",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    if profile == "dashscope:text-embedding-v2" and os.getenv("DASHSCOPE_API_KEY"):
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        return DashScopeEmbedding(model_name="text-embedding-v2")
    raise ValueError("Embedding profile 未配置")


def chinese_sentences(text):
    return [
        part.strip()
        for part in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", text)
        if part.strip()
    ]


class SectionTrace(TransformComponent):
    """Record the heading of each Markdown section before a later splitter."""

    def __call__(self, nodes, **kwargs):
        for node in nodes:
            text = node.get_content()
            parents = [
                part
                for part in str(node.metadata.get("header_path") or "").split("/")
                if part
            ]
            heading = re.match(r"^(#{1,6})\s+([^\n]+)", text)
            if heading:
                node.metadata["section_path"] = "/".join(
                    [*parents, heading.group(2).strip()]
                )
            clause = clause_of(text)
            if clause and not node.metadata.get("clause_no"):
                node.metadata["clause_no"] = clause
        return nodes


def node_parsers(strategy, size, overlap, embed=None):
    sentence = SentenceSplitter(chunk_size=size, chunk_overlap=overlap)
    if strategy in {"structure", "sentence"}:
        return [sentence]
    if strategy == "token":
        return [TokenTextSplitter(chunk_size=size, chunk_overlap=overlap)]
    if strategy == "markdown":
        return [MarkdownNodeParser(), SectionTrace(), sentence]
    if strategy == "sentence_window":
        return [
            SentenceWindowNodeParser.from_defaults(
                sentence_splitter=chinese_sentences, window_size=3
            )
        ]
    if strategy == "hierarchical":
        return [
            HierarchicalNodeParser.from_defaults(
                chunk_sizes=[size * 4, size * 2, size], chunk_overlap=overlap
            )
        ]
    if embed is None:
        raise ValueError("语义切片需要可用的向量模型")
    if strategy == "semantic":
        return [
            SemanticSplitterNodeParser.from_defaults(
                embed_model=embed, sentence_splitter=chinese_sentences
            )
        ]
    if strategy == "semantic_merge":
        return [
            SemanticDoubleMergingSplitterNodeParser.from_defaults(
                embed_model=embed,
                sentence_splitter=chinese_sentences,
                max_chunk_size=max(size * 4, 200),
            )
        ]
    raise ValueError("不支持的切片策略")


def covered(text, start, end, spans):
    hits = [meta for left, right, meta in spans if not (right <= start or left >= end)]
    if hits:
        return hits
    found = text.find(text[start:end]) if start is not None else -1
    return [meta for left, right, meta in spans if found >= 0 and not (right <= found or left >= found + (end - start))]


def source_span(node, origin):
    content = node.get_content()
    page_text, spans = origin
    start = node.start_char_idx
    if (
        isinstance(start, int)
        and page_text[start : start + len(content)] == content
    ):
        return covered(page_text, start, start + len(content), spans)
    found = page_text.find(content)
    if found < 0:
        return []
    return covered(page_text, found, found + len(content), spans)


def apply_source(metadata, hits):
    if not hits:
        return
    metadata["page_pdf"] = hits[0].get("page_pdf")
    if metadata["page_pdf"] is not None:
        metadata["docmind_page_num"] = metadata["page_pdf"] - 1
    sections_seen = []
    for meta in hits:
        path = meta.get("section_path")
        if path and path not in sections_seen:
            sections_seen.append(path)
    if sections_seen:
        metadata["section_path"] = " / ".join(sections_seen)
    if not metadata.get("clause_no"):
        for meta in hits:
            if meta.get("clause_no"):
                metadata["clause_no"] = meta["clause_no"]
                break
    for key, field in (
        ("docmind_layout_ids", "docmind_layout_ids"),
        ("docmind_layout_indexes", "docmind_layout_indexes"),
        ("layout_type", "layout_type"),
        ("layout_subtype", "layout_subtype"),
        ("content_type", "content_type"),
    ):
        values = []
        for meta in hits:
            value = meta.get(field)
            if value is not None and str(value) not in values:
                values.append(str(value))
        if values:
            metadata[key] = ",".join(values)


def index_nodes(source, parsed_dir, meta):
    origins = {}
    if source.suffix == ".pdf":
        parsed = parsed_dir / "document.json"
        if not parsed.exists():
            from docmind_parse import parse_document

            parse_document(source, parsed_dir, vlm=True, formula=True)
        parts = ((text, location, None) for text, location in sections(json.loads(parsed.read_bytes())))
    else:
        markdown = source.read_text()
        pages = pages_from_markdown(markdown, parsed_dir)
        if pages:
            parts = pages
        elif meta["chunk_strategy"] == "structure":
            parts = (
                (
                    p,
                    {
                        "section_path": p.splitlines()[0].lstrip("# ").strip()
                        if p.startswith("#")
                        else ""
                    },
                    None,
                )
                for p in re.split(r"\n(?=#{1,6}\s)", markdown)
                if p.strip()
            )
        else:
            parts = (
                (
                    markdown,
                    {
                        "section_path": markdown.splitlines()[0].lstrip("# ").strip()
                        if markdown.startswith("#")
                        else ""
                    },
                    None,
                ),
            )
    embed = (
        model(meta["embedding_profile_id"])
        if meta["chunk_strategy"] in {"semantic", "semantic_merge"}
        else None
    )
    docs = []
    for text, location, spans in parts:
        metadata = {k: v for k, v in (meta | location).items() if v is not None}
        document = Document(
            text=text,
            metadata=metadata,
            excluded_embed_metadata_keys=list(metadata),
            excluded_llm_metadata_keys=list(metadata),
        )
        if spans:
            origins[document.id_] = (text, spans)
            metadata = dict(metadata)
            metadata["page_doc"] = document.id_
            document.metadata = metadata
            document.excluded_embed_metadata_keys = list(metadata)
            document.excluded_llm_metadata_keys = list(metadata)
        docs.append(document)
    nodes = IngestionPipeline(
        transformations=node_parsers(
            meta["chunk_strategy"], meta["chunk_size"], meta["chunk_overlap"], embed
        ),
        disable_cache=True,
    ).run(documents=docs)
    if not nodes:
        raise ValueError("文档没有可索引正文")
    for i, node in enumerate(nodes):
        node.id_ = hashlib.sha256(f"{meta['index_version']}/{i}".encode()).hexdigest()
        metadata = {
            key: value
            for key, value in node.metadata.items()
            if isinstance(value, (str, int, float, bool)) and key != "page_doc"
        }
        origin_id = node.metadata.get("page_doc")
        if origin_id is None:
            relation = node.relationships.get(NodeRelationship.SOURCE)
            origin_id = getattr(relation, "node_id", None)
        if origin_id in origins:
            apply_source(metadata, source_span(node, origins[origin_id]))
        heading = re.match(r"^(#{1,6})\s+([^\n]+)", node.get_content())
        if heading and not metadata.get("section_path"):
            parents = [
                part
                for part in str(metadata.get("header_path") or "").split("/")
                if part
            ]
            metadata["section_path"] = "/".join([*parents, heading.group(2).strip()])
        clause = clause_of(node.get_content())
        if clause and not metadata.get("clause_no"):
            metadata["clause_no"] = clause
        metadata["chunk_index"] = i
        node.metadata = metadata
        node.excluded_embed_metadata_keys = list(metadata)
        node.excluded_llm_metadata_keys = list(metadata)
    return nodes


_chroma_clients = {}
_chroma_lock = threading.Lock()


def client(root):
    """One client per index path. Concurrent PersistentClient() calls race and fail."""
    path = str(root / "chroma")
    with _chroma_lock:
        cached = _chroma_clients.get(path)
        if cached is None:
            import chromadb

            cached = chromadb.PersistentClient(path=path)
            _chroma_clients[path] = cached
        return cached


def build(root, registry, job, source, parsed_dir, config):
    collection = None
    try:
        registry.stage(job, "parsing")
        nodes = index_nodes(source, parsed_dir, config)
        registry.stage(job, "embedding")
        embed = model(config["embedding_profile_id"])
        dimension = len(embed.get_query_embedding("管道"))
        if dimension != config["embedding_dimension"]:
            raise ValueError("embedding dimension changed")
        from llama_index.vector_stores.chroma import ChromaVectorStore

        collection = client(root).create_collection(job)
        store = ChromaVectorStore(chroma_collection=collection)
        IngestionPipeline(
            transformations=[embed], vector_store=store, disable_cache=True
        ).run(nodes=nodes)
        if collection.count() != len(nodes):
            raise ValueError("incomplete index")
        registry.finish(job, len(nodes), nodes)
    except Exception as exc:
        registry.fail(
            job, f"导入失败 ({type(exc).__name__})，请检查解析附件和模型连接。"
        )
        if collection is not None:
            client(root).delete_collection(job)
