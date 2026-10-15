import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langchain_core.documents import Document

from app.langchain_pipeline import LangChainRagPipeline
from app.server import main as start_server


class CloudRunDeploymentTests(unittest.TestCase):
    def test_server_uses_cloud_run_port(self):
        with patch.dict(os.environ, {"PORT": "8080", "TRUST_PROXY_HEADERS": "true"}, clear=False):
            with patch("app.server.uvicorn.run") as run:
                start_server()

        self.assertEqual(run.call_args.kwargs["port"], 8080)
        self.assertEqual(run.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(run.call_args.kwargs["forwarded_allow_ips"], "*")

    def test_remote_langchain_result_does_not_require_local_chunk_file(self):
        remote_document = Document(
            page_content="Isi dokumen dari pgvector.",
            metadata={
                "chunk_id": "remote-1",
                "document_title": "Panduan Mualaf",
                "page_number": 7,
                "file_name": "panduan.pdf",
                "score": 0.91,
            },
        )

        class FakeRetriever:
            def __init__(self, vector_store, top_k):
                pass

            def invoke(self, query):
                return [remote_document]

        pipeline = object.__new__(LangChainRagPipeline)
        pipeline.vector_store = type("RemoteStore", (), {"chunks": []})()

        with patch("app.langchain_pipeline.LangChainVectorStoreRetriever", FakeRetriever):
            results = pipeline._retrieve_results("syahadat", 4)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, "remote-1")
        self.assertEqual(results[0].chunk.page_number, 7)
        self.assertAlmostEqual(results[0].score, 0.91)


if __name__ == "__main__":
    unittest.main()
