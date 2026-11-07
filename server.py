"""Authoritative UDP server for the Tug-of-War Button Masher.

Run: python server.py --host 0.0.0.0 --port 9999
"""

from __future__ import annotations

import argparse
import os
import random
import socket
import threading
import time
from dataclasses import dataclass

from common import NetworkExperiment, decode, encode, now_ms


@dataclass
class Peer:
    address: tuple[str, int]
    name: str
    role: str
    symbol: str | None = None
    last_seq: int = -1
    last_seen: float = 0.0


class GameServer:
    def __init__(self, host: str, port: int, loss: float = 0.0, delay_ms: int = 0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if os.getenv("GAME_DSCP") == "46":
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 46 << 2)
        self.sock.bind((host, port))
        self.experiment = NetworkExperiment(loss, delay_ms)
        self.peers: dict[tuple[str, int], Peer] = {}
        self.rope = 0
        self.clicks = {"left": 0, "right": 0}
        self.winner: str | None = None
        self.game_id = random.randint(1000, 9999)
        self.lock = threading.Lock()

    def send(self, address, message, apply_experiment=True):
        if apply_experiment and self.experiment.drop():
            return
        if apply_experiment:
            self.experiment.delay()
        try:
            self.sock.sendto(encode(message), address)
        except OSError:
            pass

    def broadcast(self, message):
        for peer in list(self.peers.values()):
            self.send(peer.address, message)

    def state(self):
        return {
            "type": "state",
            "game_id": self.game_id,
            "rope": self.rope,
            "clicks": self.clicks,
            "winner": self.winner,
            "players": [
                {"name": p.name, "role": p.role, "symbol": p.symbol}
                for p in self.peers.values()
            ],
            "server_time": now_ms(),
        }

    def reset(self):
        self.rope = 0
        self.clicks = {"left": 0, "right": 0}
        self.winner = None
        self.game_id = random.randint(1000, 9999)

    def register(self, address, msg):
        if address in self.peers:
            return
        players = [p for p in self.peers.values() if p.role == "player"]
        role = "player" if len(players) < 2 and msg.get("role") != "spectator" else "spectator"
        symbol = "X" if role == "player" and not any(p.symbol == "X" for p in players) else "O" if role == "player" else None
        name = str(msg.get("name", "guest"))[:20]
        self.peers[address] = Peer(address, name, role, symbol, last_seen=time.time())
        self.send(address, {"type": "registered", "role": role, "symbol": symbol}, apply_experiment=False)
        self.broadcast({"type": "notice", "text": f"{name} joined as {role}."})
        self.broadcast(self.state())

    def move(self, address, msg):
        peer = self.peers.get(address)
        if not peer or peer.role != "player":
            return
        seq = int(msg.get("seq", -1))
        if seq <= peer.last_seq:
            self.send(address, {"type": "ack", "seq": seq, "duplicate": True}, apply_experiment=False)
            return
        peer.last_seq = seq
        self.send(address, {"type": "ack", "seq": seq}, apply_experiment=False)
        if self.winner:
            return
        if msg.get("type") != "pull":
            return
        side = "left" if peer.symbol == "X" else "right"
        amount = max(1, min(5, int(msg.get("amount", 1))))
        self.clicks[side] += amount
        self.rope += amount if side == "left" else -amount
        if self.rope >= 100:
            self.winner = "LEFT"
        elif self.rope <= -100:
            self.winner = "RIGHT"
        if self.winner:
            self.broadcast({"type": "notice", "text": f"{self.winner} player wins!"})
        self.broadcast(self.state())

    def heartbeat(self):
        """Remove inactive peers so new players can join after disconnects."""
        while True:
            time.sleep(2)
            with self.lock:
                stale = [a for a, p in self.peers.items() if time.time() - p.last_seen > 15]
                for address in stale:
                    self.peers.pop(address, None)
                if stale:
                    self.broadcast({"type": "notice", "text": "A player disconnected."})
                    self.broadcast(self.state())

    def run(self):
        print(f"UDP Tug-of-War server listening on {self.sock.getsockname()}")
        threading.Thread(target=self.heartbeat, daemon=True).start()
        while True:
            try:
                data, address = self.sock.recvfrom(65535)
            except KeyboardInterrupt:
                break
            msg = decode(data)
            if not msg:
                continue
            with self.lock:
                if msg.get("type") == "register":
                    self.register(address, msg)
                elif address in self.peers:
                    self.peers[address].last_seen = time.time()
                    if msg.get("type") == "pull":
                        self.move(address, msg)
                    elif msg.get("type") == "reset":
                        self.reset()
                        self.broadcast(self.state())
                    elif msg.get("type") == "ping":
                        # Control/measurement packets are high priority and bypass loss simulation.
                        self.send(address, {"type": "pong", "sent": msg.get("sent")}, apply_experiment=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--loss", type=float, default=0.0, help="artificial UDP loss from 0 to 1")
    parser.add_argument("--delay-ms", type=int, default=0)
    args = parser.parse_args()
    GameServer(args.host, args.port, args.loss, args.delay_ms).run()
