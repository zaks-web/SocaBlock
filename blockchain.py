import hashlib
import json
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Block:
    def __init__(self, index, timestamp, transactions, previous_hash, nonce=0, block_hash=None, difficulty=0):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.difficulty = difficulty
        self.hash = block_hash or self.calculate_hash()

    def calculate_hash(self):
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        if self.difficulty:
            payload["difficulty"] = self.difficulty
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def mine(self):
        if self.difficulty < 0:
            raise ValueError("La difficulté ne peut pas être négative.")
        self.hash = self.calculate_hash()
        while not self.hash.startswith("0" * self.difficulty):
            self.nonce += 1
            self.hash = self.calculate_hash()
        return self.hash

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "hash": self.hash,
        }


class Blockchain:
    """Prototype pédagogique : un bloc est créé à chaque transfert validé."""

    def __init__(self):
        self.chain = []

    def create_genesis_block(self):
        block = Block(0, utc_now(), [{"type": "GENESIS", "message": "Bienvenue sur SocaBlock"}], "0" * 64)
        self.chain.append(block)
        return block

    def add_block(self, transactions, difficulty=0):
        if not self.chain:
            self.create_genesis_block()
        previous = self.chain[-1]
        block = Block(len(self.chain), utc_now(), transactions, previous.hash, difficulty=difficulty)
        block.mine()
        self.chain.append(block)
        return block

    def is_valid(self):
        if not self.chain:
            return False
        for i, block in enumerate(self.chain):
            if block.hash != block.calculate_hash():
                return False
            if block.difficulty < 0 or not block.hash.startswith("0" * block.difficulty):
                return False
            if i == 0:
                if block.previous_hash != "0" * 64:
                    return False
            elif block.previous_hash != self.chain[i - 1].hash:
                return False
        return True
