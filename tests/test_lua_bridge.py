import json
from pathlib import Path
import pytest

lupa = pytest.importorskip("lupa")
BRIDGE = Path(__file__).parents[1] / "src/composer_rostrum/backends/reaper/bridge"


def test_lua_codec_unicode_arrays_null_and_escaping():
    lua = lupa.LuaRuntime()
    codec = lua.eval("dofile")(str(BRIDGE / "json.lua"))
    value = {"unicode": "music 🎵 é", "empty": [], "none": None, "nested": [{"a": True}], "escape": "\n\t\"\\"}
    assert json.loads(codec.encode(codec.decode(json.dumps(value)))) == value
    assert json.loads(codec.encode(codec.decode(json.dumps(value, ensure_ascii=False)))) == value


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '[1,]', '"\\uDC00"', '"\\uD800"', '{"a":1} garbage', '01', '1.', '1.e2', 'NaN'])
def test_lua_codec_rejects_invalid_protocol_json(value):
    lua = lupa.LuaRuntime()
    codec = lua.eval("dofile")(str(BRIDGE / "json.lua"))
    with pytest.raises(lupa.LuaError):
        codec.decode(value)


@pytest.mark.parametrize("prefix", ["", "//?/"])
def test_bridge_compiles_and_answers_atomic_handshake(tmp_path, prefix):
    (tmp_path / "requests").mkdir()
    (tmp_path / "responses").mkdir()
    request = {"protocol": 1, "id": "000001", "command": "ping", "arguments": {}}
    (tmp_path / "requests/000001.json").write_text(json.dumps(request), encoding="utf-8")
    lua = lupa.LuaRuntime()
    lua.globals().ROSTRUM_WORKSPACE = prefix + tmp_path.as_posix()
    lua.execute("reaper={GetAppVersion=function() return 'test' end, EnumerateFiles=function(path,i) if i==0 then return '000001.json' end end, defer=function(f) end}")
    lua.eval("dofile")(str(BRIDGE / "rostrum_bridge.lua"))
    response = json.loads((tmp_path / "responses/000001.json").read_text())
    assert response["ok"] and response["result"]["pong"]
    assert not (tmp_path / "responses/000001.json.tmp").exists()
