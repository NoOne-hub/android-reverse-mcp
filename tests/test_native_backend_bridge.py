import pytest

from android_reverse_mcp.native_backends.bridge import (
    DEFAULT_IDA_TOOL_MAPPING,
    NativeBackendConfig,
    create_native_backend,
    parse_native_backend_config,
)
from android_reverse_mcp.native_backends.ghidra import GhidraBackend
from android_reverse_mcp.native_backends.ida import IdaBackend


def test_parse_native_backend_config_prefers_generic_env(monkeypatch):
    monkeypatch.setenv("NATIVE_BACKEND", "ida")
    monkeypatch.setenv("NATIVE_BACKEND_URL", "http://ida-sidecar:8745/mcp")

    config = parse_native_backend_config()

    assert config == NativeBackendConfig(name="ida", url="http://ida-sidecar:8745/mcp")


def test_parse_native_backend_config_falls_back_to_ghidra_env(monkeypatch):
    monkeypatch.delenv("NATIVE_BACKEND", raising=False)
    monkeypatch.delenv("NATIVE_BACKEND_URL", raising=False)
    monkeypatch.setenv("GHIDRA_BACKEND", "tcp://ghidra-sidecar:8765")

    config = parse_native_backend_config()

    assert config == NativeBackendConfig(name="ghidra", url="tcp://ghidra-sidecar:8765")


def test_parse_native_backend_config_rejects_partial_generic_config(monkeypatch):
    monkeypatch.setenv("NATIVE_BACKEND", "ida")
    monkeypatch.delenv("NATIVE_BACKEND_URL", raising=False)
    monkeypatch.setenv("GHIDRA_BACKEND", "tcp://ghidra-sidecar:8765")

    with pytest.raises(RuntimeError, match="native backend 配置不完整"):
        parse_native_backend_config()


def test_parse_native_backend_config_raises_when_unset(monkeypatch):
    monkeypatch.delenv("NATIVE_BACKEND", raising=False)
    monkeypatch.delenv("NATIVE_BACKEND_URL", raising=False)
    monkeypatch.delenv("GHIDRA_BACKEND", raising=False)

    with pytest.raises(RuntimeError, match="native backend 未配置"):
        parse_native_backend_config()


def test_create_native_backend_returns_ghidra_backend():
    backend = create_native_backend("ghidra", "tcp://ghidra-sidecar:8765")

    assert isinstance(backend, GhidraBackend)
    assert backend.url == "tcp://ghidra-sidecar:8765"


def test_create_native_backend_returns_ida_backend():
    backend = create_native_backend("ida", "http://ida-sidecar:8745/mcp")

    assert isinstance(backend, IdaBackend)
    assert backend.url == "http://ida-sidecar:8745/mcp"
    assert backend.tool_mapping == DEFAULT_IDA_TOOL_MAPPING


def test_create_native_backend_passes_explicit_ida_tool_mapping():
    backend = create_native_backend(
        "ida",
        "http://ida-sidecar:8745/mcp",
        tool_mapping={"list_functions": "custom.list_functions"},
    )

    assert isinstance(backend, IdaBackend)
    assert backend.url == "http://ida-sidecar:8745/mcp"
    expected = dict(DEFAULT_IDA_TOOL_MAPPING)
    expected["list_functions"] = "custom.list_functions"
    assert backend.tool_mapping == expected


def test_create_native_backend_raises_for_unknown_backend():
    with pytest.raises(ValueError, match="unsupported native backend: binaryninja"):
        create_native_backend("binaryninja", "tcp://binaryninja-sidecar:8767")
