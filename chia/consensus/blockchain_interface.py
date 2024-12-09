from __future__ import annotations

from typing import Optional, Protocol

from chia.consensus.block_record import BlockRecord
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.blockchain_format.sub_epoch_summary import SubEpochSummary
from chia.types.header_block import HeaderBlock
from chia.types.weight_proof import SubEpochChallengeSegment
from chia.util.ints import uint32


class BlockRecordsProtocol(Protocol):
    def try_block_record(self, header_hash: bytes32) -> Optional[BlockRecord]: ...
    def block_record(self, header_hash: bytes32) -> BlockRecord: ...
    def contains_height(self, height: uint32) -> bool: ...
    def get_peak_height(self) -> Optional[uint32]: ...
    def contains_block(self, header_hash: bytes32) -> bool: ...
    def height_to_hash(self, height: uint32) -> Optional[bytes32]: ...
    def height_to_block_record(self, height: uint32) -> BlockRecord: ...

    # given a list of block header hashes, return the header hashes of their
    # previous blocks. This is not limited to the block record cache, but must
    # allow any block in the database to be referenced
    async def prev_block_hash(self, header_hashes: list[bytes32]) -> list[bytes32]: ...


class BlocksProtocol(BlockRecordsProtocol, Protocol):
    async def lookup_block_generators(
        self, header_hash: bytes32, generator_refs: set[uint32]
    ) -> dict[uint32, bytes]: ...
    async def get_block_record_from_db(self, header_hash: bytes32) -> Optional[BlockRecord]: ...
    def add_block_record(self, block_record: BlockRecord) -> None: ...


class BlockchainInterface(BlocksProtocol, Protocol):
    def get_peak(self) -> Optional[BlockRecord]: ...
    def get_peak_height(self) -> Optional[uint32]: ...
    def get_ses_heights(self) -> list[uint32]: ...
    def get_ses(self, height: uint32) -> SubEpochSummary: ...
    async def contains_block_from_db(self, header_hash: bytes32) -> bool: ...
    async def get_block_records_in_range(self, start: int, stop: int) -> dict[bytes32, BlockRecord]: ...

    async def get_header_blocks_in_range(
        self, start: int, stop: int, tx_filter: bool = True
    ) -> dict[bytes32, HeaderBlock]: ...

    async def get_block_records_at(self, heights: list[uint32]) -> list[BlockRecord]: ...

    async def persist_sub_epoch_challenge_segments(
        self, sub_epoch_summary_hash: bytes32, segments: list[SubEpochChallengeSegment]
    ) -> None: ...

    async def get_sub_epoch_challenge_segments(
        self,
        sub_epoch_summary_hash: bytes32,
    ) -> Optional[list[SubEpochChallengeSegment]]: ...
