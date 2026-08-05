from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"


@dataclass
class Property:
    code: bytes
    value: object = None
    raw: bytes | None = None

    def encoded(self) -> bytes:
        if self.raw is not None:
            return self.code + self.raw
        if self.code == b"Y":
            return self.code + struct.pack("<h", int(self.value))
        if self.code == b"C":
            return self.code + struct.pack("<?", bool(self.value))
        if self.code == b"I":
            return self.code + struct.pack("<i", int(self.value))
        if self.code == b"F":
            return self.code + struct.pack("<f", float(self.value))
        if self.code == b"D":
            return self.code + struct.pack("<d", float(self.value))
        if self.code == b"L":
            return self.code + struct.pack("<q", int(self.value))
        if self.code in {b"S", b"R"}:
            data = self.value if self.code == b"R" else str(self.value).encode("utf-8")
            if not isinstance(data, bytes):
                raise TypeError("Raw FBX property data must be bytes")
            return self.code + struct.pack("<I", len(data)) + data
        if self.code in {b"f", b"d", b"l", b"i", b"b"}:
            values = list(self.value)
            formats = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "?"}
            packed = struct.pack("<" + formats[self.code] * len(values), *values)
            return self.code + struct.pack("<III", len(values), 0, len(packed)) + packed
        raise ValueError(f"Unsupported FBX property type: {self.code!r}")


@dataclass
class Node:
    name: bytes
    properties: list[Property] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)

    def child(self, name: bytes) -> "Node | None":
        return next((child for child in self.children if child.name == name), None)

    def children_named(self, name: bytes) -> list["Node"]:
        return [child for child in self.children if child.name == name]

    def prop(self, index: int, default=None):
        return self.properties[index].value if len(self.properties) > index else default


class FBXBinary:
    def __init__(self, version: int, roots: list[Node]) -> None:
        self.version = version
        self.roots = roots

    @property
    def header_size(self) -> int:
        return 27

    @property
    def null_size(self) -> int:
        return 25 if self.version >= 7500 else 13

    @classmethod
    def read(cls, path: str) -> "FBXBinary":
        with open(path, "rb") as handle:
            data = handle.read()
        if not data.startswith(MAGIC):
            raise ValueError("Not a binary FBX file")
        version = struct.unpack_from("<I", data, 23)[0]
        parser = _Parser(data, version)
        roots = []
        while parser.pos + parser.null_size < len(data):
            node = parser.node()
            if node is None:
                break
            roots.append(node)
        return cls(version, roots)

    def write(self, path: str) -> None:
        output = bytearray(MAGIC)
        output.extend(struct.pack("<I", self.version))
        position = len(output)
        for node in self.roots:
            encoded = _encode_node(node, self.version, position)
            output.extend(encoded)
            position += len(encoded)
        output.extend(b"\x00" * self.null_size)
        with open(path, "wb") as handle:
            handle.write(output)


class _Parser:
    def __init__(self, data: bytes, version: int) -> None:
        self.data = data
        self.version = version
        self.pos = 27
        self.header = 25 if version >= 7500 else 13
        self.null_size = 25 if version >= 7500 else 13

    def _unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        value = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return value[0] if len(value) == 1 else value

    def node(self) -> Node | None:
        start = self.pos
        if start + self.header > len(self.data):
            return None
        if self.data[start : start + self.null_size] == b"\x00" * self.null_size:
            self.pos += self.null_size
            return None
        if self.version >= 7500:
            end_offset, prop_count, _prop_len, name_len = self._unpack("<QQQB")
        else:
            end_offset, prop_count, _prop_len, name_len = self._unpack("<IIIB")
        name = self.data[self.pos : self.pos + name_len]
        self.pos += name_len
        properties = [self.property() for _index in range(prop_count)]
        node = Node(name=name, properties=properties)
        child_end = end_offset - self.null_size
        while self.pos < child_end:
            child = self.node()
            if child is None:
                break
            node.children.append(child)
        self.pos = end_offset
        return node

    def property(self) -> Property:
        code = self.data[self.pos : self.pos + 1]
        self.pos += 1
        scalar_formats = {b"Y": "<h", b"C": "<?", b"I": "<i", b"F": "<f", b"D": "<d", b"L": "<q"}
        if code in scalar_formats:
            size = struct.calcsize(scalar_formats[code])
            value = struct.unpack(scalar_formats[code], self.data[self.pos : self.pos + size])[0]
            self.pos += size
            return Property(code, value)
        if code in {b"S", b"R"}:
            length = self._unpack("<I")
            value = self.data[self.pos : self.pos + length]
            self.pos += length
            return Property(code, value.decode("utf-8", errors="replace") if code == b"S" else value)
        if code in {b"f", b"d", b"l", b"i", b"b"}:
            length, encoding, encoded_length = self._unpack("<III")
            encoded_raw = self.data[self.pos : self.pos + encoded_length]
            self.pos += encoded_length
            raw = zlib.decompress(encoded_raw) if encoding == 1 else encoded_raw
            if encoding not in {0, 1}:
                raise ValueError(f"Unsupported FBX array encoding: {encoding}")
            formats = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "?"}
            item_size = struct.calcsize(formats[code])
            values = struct.unpack("<" + formats[code] * length, raw[: item_size * length])
            return Property(code, list(values), struct.pack("<III", length, encoding, encoded_length) + encoded_raw)
        raise ValueError(f"Unsupported FBX property type: {code!r}")


def _encode_node(node: Node, version: int, start: int) -> bytes:
    props = b"".join(prop.encoded() for prop in node.properties)
    name = node.name
    child_data = b"".join(_encode_node(child, version, 0) for child in node.children)
    null_size = 25 if version >= 7500 else 13
    header_size = 25 if version >= 7500 else 13
    end_offset = start + header_size + len(name) + len(props) + len(child_data) + null_size
    if version >= 7500:
        header = struct.pack("<QQQB", end_offset, len(node.properties), len(props), len(name))
    else:
        header = struct.pack("<IIIB", end_offset, len(node.properties), len(props), len(name))
    data = bytearray(header + name + props)
    child_start = start + len(data)
    for child in node.children:
        encoded = _encode_node(child, version, child_start)
        data.extend(encoded)
        child_start += len(encoded)
    data.extend(b"\x00" * null_size)
    return bytes(data)


def string_property(value: str) -> Property:
    return Property(b"S", value)


def array_property(values: list[float]) -> Property:
    return Property(b"d", values)
