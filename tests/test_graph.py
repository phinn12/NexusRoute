from pathlib import Path

from kargo_backend.graph import invalidate_broken_graph_cache


def test_invalidate_broken_graph_cache_removes_zero_byte_file(tmp_path):
    graph_path = tmp_path / "broken.graphml"
    graph_path.write_bytes(b"")

    invalidate_broken_graph_cache(graph_path)

    assert not graph_path.exists()
