from __future__ import annotations

import hashlib
import struct
from dataclasses import astuple, dataclass
from random import Random
from typing import Callable, Dict, Generic, List, Set, Type, TypeVar, final

import chia_rs
import pytest

# TODO: update after resolution in https://github.com/pytest-dev/pytest/issues/7469
from _pytest.fixtures import SubRequest

from chia._tests.util.misc import DataCase, Marks, datacases
from chia.data_layer.util.merkle_blob import (
    InvalidIndexError,
    KVId,
    MerkleBlob,
    NodeMetadata,
    NodeType,
    RawInternalMerkleNode,
    RawLeafMerkleNode,
    RawMerkleNodeProtocol,
    TreeIndex,
    data_size,
    metadata_size,
    null_parent,
    pack_raw_node,
    raw_node_classes,
    raw_node_type_to_class,
    spacing,
    unpack_raw_node,
)

# class MerkleBlobProtocol(Protocol):
#     def __init__(self, blob: bytearray) -> None: ...
#     def insert(self, key_value: KVId, hash: bytes) -> None: ...


@pytest.fixture(
    name="merkle_blob_type",
    params=[MerkleBlob, chia_rs.MerkleBlob],
    ids=["python", "rust"],
)
def merkle_blob_type_fixture(request: SubRequest) -> Callable[[...], MerkleBlob]:
    return MerkleBlob


@pytest.fixture(
    name="raw_node_class",
    scope="session",
    params=raw_node_classes,
    ids=[cls.type.name for cls in raw_node_classes],
)
def raw_node_class_fixture(request: SubRequest) -> RawMerkleNodeProtocol:
    # https://github.com/pytest-dev/pytest/issues/8763
    return request.param  # type: ignore[no-any-return]


class_to_structs: Dict[Type[object], struct.Struct] = {
    NodeMetadata: NodeMetadata.struct,
    **{cls: cls.struct for cls in raw_node_classes},
}


@pytest.fixture(
    name="class_struct",
    scope="session",
    params=class_to_structs.values(),
    ids=[cls.__name__ for cls in class_to_structs.keys()],
)
def class_struct_fixture(request: SubRequest) -> RawMerkleNodeProtocol:
    # https://github.com/pytest-dev/pytest/issues/8763
    return request.param  # type: ignore[no-any-return]


def test_raw_node_class_types_are_unique() -> None:
    assert len(raw_node_type_to_class) == len(raw_node_classes)


def test_metadata_size_not_changed() -> None:
    assert metadata_size == 2


def test_data_size_not_changed() -> None:
    assert data_size == 44


def test_raw_node_struct_sizes(raw_node_class: RawMerkleNodeProtocol) -> None:
    assert raw_node_class.struct.size == data_size


def test_all_big_endian(class_struct: struct.Struct) -> None:
    assert class_struct.format.startswith(">")


# TODO: check all struct types against attribute types

RawMerkleNodeT = TypeVar("RawMerkleNodeT", bound=RawMerkleNodeProtocol)


reference_blob = bytes(range(data_size))


@final
@dataclass
class RawNodeFromBlobCase(Generic[RawMerkleNodeT]):
    raw: RawMerkleNodeT
    blob_to_unpack: bytes = reference_blob
    packed_blob_reference: bytes = reference_blob

    marks: Marks = ()

    @property
    def id(self) -> str:
        return self.raw.type.name


reference_raw_nodes: List[DataCase] = [
    RawNodeFromBlobCase(
        raw=RawInternalMerkleNode(
            parent=TreeIndex(0x00010203),
            left=TreeIndex(0x04050607),
            right=TreeIndex(0x08090A0B),
            hash=bytes(range(12, data_size)),
            index=TreeIndex(0),
        ),
    ),
    RawNodeFromBlobCase(
        raw=RawLeafMerkleNode(
            parent=TreeIndex(0x00010203),
            key_value=KVId(0x0405060708090A0B),
            hash=bytes(range(12, data_size)),
            index=TreeIndex(0),
        ),
    ),
]


@datacases(*reference_raw_nodes)
def test_raw_node_from_blob(case: RawNodeFromBlobCase[RawMerkleNodeProtocol]) -> None:
    node = unpack_raw_node(
        index=TreeIndex(0),
        metadata=NodeMetadata(type=case.raw.type, dirty=False),
        data=case.blob_to_unpack,
    )
    assert node == case.raw


@datacases(*reference_raw_nodes)
def test_raw_node_to_blob(case: RawNodeFromBlobCase[RawMerkleNodeProtocol]) -> None:
    blob = pack_raw_node(case.raw)
    assert blob == case.packed_blob_reference


def test_merkle_blob_one_leaf_loads() -> None:
    # TODO: need to persist reference data
    leaf = RawLeafMerkleNode(
        parent=null_parent,
        key_value=KVId(0x0405060708090A0B),
        hash=bytes(range(12, data_size)),
        index=TreeIndex(0),
    )
    blob = bytearray(NodeMetadata(type=NodeType.leaf, dirty=False).pack() + pack_raw_node(leaf))

    merkle_blob = MerkleBlob(blob=blob)
    assert merkle_blob.get_raw_node(TreeIndex(0)) == leaf


def test_merkle_blob_two_leafs_loads() -> None:
    # TODO: break this test down into some reusable data and multiple tests
    # TODO: need to persist reference data
    root = RawInternalMerkleNode(
        parent=null_parent,
        left=TreeIndex(1),
        right=TreeIndex(2),
        hash=bytes(range(12, data_size)),
        index=TreeIndex(0),
    )
    left_leaf = RawLeafMerkleNode(
        parent=TreeIndex(0),
        key_value=KVId(0x0405060708090A0B),
        hash=bytes(range(12, data_size)),
        index=TreeIndex(1),
    )
    right_leaf = RawLeafMerkleNode(
        parent=TreeIndex(0),
        key_value=KVId(0x1415161718191A1B),
        hash=bytes(range(12, data_size)),
        index=TreeIndex(2),
    )
    blob = bytearray()
    blob.extend(NodeMetadata(type=NodeType.internal, dirty=True).pack() + pack_raw_node(root))
    blob.extend(NodeMetadata(type=NodeType.leaf, dirty=False).pack() + pack_raw_node(left_leaf))
    blob.extend(NodeMetadata(type=NodeType.leaf, dirty=False).pack() + pack_raw_node(right_leaf))

    merkle_blob = MerkleBlob(blob=blob)
    assert merkle_blob.get_raw_node(TreeIndex(0)) == root
    assert merkle_blob.get_raw_node(root.left) == left_leaf
    assert merkle_blob.get_raw_node(root.right) == right_leaf
    assert merkle_blob.get_raw_node(left_leaf.parent) == root
    assert merkle_blob.get_raw_node(right_leaf.parent) == root

    assert merkle_blob.get_lineage(TreeIndex(0)) == [root]
    assert merkle_blob.get_lineage(root.left) == [left_leaf, root]


def generate_kvid(seed: int) -> KVId:
    seed_bytes = seed.to_bytes(8, byteorder="big")
    hash_obj = hashlib.sha256(seed_bytes)
    hash_int = int.from_bytes(hash_obj.digest()[:8], byteorder="big")
    return KVId(hash_int)


def generate_hash(seed: int) -> bytes:
    seed_bytes = seed.to_bytes(8, byteorder="big")
    hash_obj = hashlib.sha256(seed_bytes)
    return hash_obj.digest()


def test_insert_delete_loads_all_keys() -> None:
    merkle_blob = MerkleBlob(blob=bytearray())
    num_keys = 200000
    extra_keys = 100000
    max_height = 25
    keys_values: Set[KVId] = set()

    random = Random()
    random.seed(100, version=2)
    expected_num_entries = 0
    current_num_entries = 0

    for key in range(num_keys):
        [op_type] = random.choices(["insert", "delete"], [0.7, 0.3], k=1)
        if op_type == "delete" and len(keys_values) > 0:
            kv_id = random.choice(list(keys_values))
            keys_values.remove(kv_id)
            merkle_blob.delete(kv_id)
            if current_num_entries == 1:
                current_num_entries = 0
                expected_num_entries = 0
            else:
                current_num_entries -= 2
        else:
            kv_id = generate_kvid(key)
            hash = generate_hash(key)
            merkle_blob.insert(kv_id, hash)
            key_index = merkle_blob.kv_to_index[kv_id]
            lineage = merkle_blob.get_lineage(TreeIndex(key_index))
            assert len(lineage) <= max_height
            keys_values.add(kv_id)
            if current_num_entries == 0:
                current_num_entries = 1
            else:
                current_num_entries += 2

        expected_num_entries = max(expected_num_entries, current_num_entries)
        assert len(merkle_blob.blob) // spacing == expected_num_entries

    assert set(merkle_blob.get_keys_values_indexes().keys()) == keys_values

    merkle_blob_2 = MerkleBlob(blob=merkle_blob.blob)
    unknown_key = KVId(42)
    for key in range(num_keys, num_keys + extra_keys):
        kv_id = generate_kvid(key)
        hash = generate_hash(key)
        merkle_blob_2.upsert(unknown_key, kv_id, hash)
        key_index = merkle_blob_2.kv_to_index[kv_id]
        lineage = merkle_blob_2.get_lineage(TreeIndex(key_index))
        assert len(lineage) <= max_height
        keys_values.add(kv_id)
    assert set(merkle_blob_2.get_keys_values_indexes().keys()) == keys_values


def test_small_insert_deletes() -> None:
    merkle_blob = MerkleBlob(blob=bytearray())
    num_repeats = 100
    max_inserts = 25
    seed = 0

    random = Random()
    random.seed(100, version=2)

    for repeats in range(num_repeats):
        for num_inserts in range(max_inserts):
            keys_values: List[KVId] = []
            for inserts in range(num_inserts):
                seed += 1
                kv_id = generate_kvid(seed)
                hash = generate_hash(seed)
                merkle_blob.insert(kv_id, hash)
                keys_values.append(kv_id)

            random.shuffle(keys_values)
            remaining_keys_values = set(keys_values)
            for kv_id in keys_values:
                merkle_blob.delete(kv_id)
                remaining_keys_values.remove(kv_id)
                assert set(merkle_blob.get_keys_values_indexes().keys()) == remaining_keys_values
            assert remaining_keys_values == set()


def test_proof_of_inclusion_merkle_blob() -> None:
    num_repeats = 10
    num_inserts = 1000
    num_deletes = 100
    seed = 0

    random = Random()
    random.seed(100, version=2)

    merkle_blob = MerkleBlob(blob=bytearray())
    keys_values: List[KVId] = []

    for repeats in range(num_repeats):
        for _ in range(num_inserts):
            seed += 1
            kv_id = generate_kvid(seed)
            hash = generate_hash(seed)
            merkle_blob.insert(kv_id, hash)
            keys_values.append(kv_id)

        random.shuffle(keys_values)
        for kv_id in keys_values[:num_deletes]:
            merkle_blob.delete(kv_id)
        keys_values = keys_values[num_deletes:]

        merkle_blob.calculate_lazy_hashes()
        for kv_id in keys_values:
            proof_of_inclusion = merkle_blob.get_proof_of_inclusion(kv_id)
            assert proof_of_inclusion.valid()

        new_keys_values: List[KVId] = []
        for old_kv in keys_values:
            seed += 1
            kv_id = generate_kvid(seed)
            hash = generate_hash(seed)
            merkle_blob.upsert(old_kv, kv_id, hash)
            new_keys_values.append(kv_id)

        merkle_blob.calculate_lazy_hashes()
        for kv_id in keys_values:
            with pytest.raises(Exception, match=f"Key {kv_id} not present in the store"):
                merkle_blob.get_proof_of_inclusion(kv_id)
        keys_values = new_keys_values
        for kv_id in keys_values:
            proof_of_inclusion = merkle_blob.get_proof_of_inclusion(kv_id)
            assert proof_of_inclusion.valid()


@pytest.mark.parametrize(argnames="index", argvalues=[TreeIndex(-1), TreeIndex(1), TreeIndex(null_parent)])
def test_get_raw_node_raises_for_invalid_indexes(index: TreeIndex) -> None:
    merkle_blob = MerkleBlob(blob=bytearray())
    merkle_blob.insert(KVId(0x1415161718191A1B), bytes(range(12, data_size)))

    with pytest.raises(InvalidIndexError):
        merkle_blob.get_raw_node(index)
        merkle_blob.get_metadata(index)


@pytest.mark.parametrize(argnames="cls", argvalues=raw_node_classes)
def test_as_tuple_matches_dataclasses_astuple(cls: Type[RawMerkleNodeProtocol], seeded_random: Random) -> None:
    raw_bytes = bytes(seeded_random.getrandbits(8) for _ in range(cls.struct.size))
    raw_node = cls(*cls.struct.unpack(raw_bytes), index=TreeIndex(seeded_random.randrange(1_000_000)))
    # hacky [:-1] to exclude the index
    # TODO: try again to indicate that the RawMerkleNodeProtocol requires the dataclass interface
    assert raw_node.as_tuple() == astuple(raw_node)[:-1]  # type: ignore[call-overload]


def test_just_insert_a_bunch(merkle_blob_type: Callable[[...], MerkleBlob]) -> None:
    HASH = bytes(range(12, 44))

    import pathlib

    path = pathlib.Path("~/tmp/mbt/").expanduser()
    path.joinpath("py").mkdir(parents=True, exist_ok=True)
    path.joinpath("rs").mkdir(parents=True, exist_ok=True)

    merkle_blob = merkle_blob_type(blob=bytearray())
    import time

    total_time = 0
    for i in range(100000):
        start = time.monotonic()
        merkle_blob.insert(i, HASH)
        end = time.monotonic()
        total_time += end - start

        # kv_count = i + 1
        # if kv_count == 2:
        #     assert len(merkle_blob.blob) == 3 * spacing
        # elif kv_count == 3:
        #     assert len(merkle_blob.blob) == 5 * spacing
        #
        # with path.joinpath("py", f"{i:04}").open(mode="w") as file:
        #     for offset in range(0, len(merkle_blob.blob), spacing):
        #         file.write(merkle_blob.blob[offset:offset + spacing].hex())
        #         file.write("\n")
        # path.joinpath("py", f"{i:04}").write_bytes(merkle_blob.blob)

    # rs = pathlib.Path(
    # "~/repos/chia_rs/crates/chia-datalayer/src/test_just_insert_a_bunch_reference").expanduser().read_bytes()
    # b = bytes(merkle_blob.blob)
    # assert b == rs, 'not the same'
    assert False, f"total time: {total_time}"
