"""Pygame UDP client for Tug-of-War Button Masher.

Run player:    python client.py --name Alice
Run spectator: python client.py --name Viewer --spectator
"""

from __future__ import annotations

import argparse
import queue
import socket
import threading
import time

from common import NetworkExperiment, decode, encode, now_ms

try:
    import pygame
except ImportError:
    pygame = None


class VoiceChat:
    """Optional microphone broadcast. Install sounddevice to enable it."""
    def __init__(self, sock, server):
        self.sock, self.server = sock, server
        self.enabled = False
        try:
            import sounddevice  # noqa: F401
            self.sd = sounddevice
            self.enabled = True
        except ImportError:
            self.sd = None

    def start(self):
        if not self.enabled:
            return False
        def capture(indata, frames, timing, status):
            packet = {"type": "voice", "audio": bytes(indata).hex()}
            self.sock.sendto(encode(packet), self.server)
        self.stream = self.sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", callback=capture, blocksize=1024)
        self.stream.start()
        return True

    def stop(self):
        if getattr(self, "stream", None):
            self.stream.stop()
            self.stream.close()


class Client:
    def __init__(self, server, name, spectator=False, loss=0.0):
        self.server = server
        self.name = name
        self.requested_role = "spectator" if spectator else "player"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 46 << 2)
        self.sock.settimeout(0.2)
        self.seq = 0
        self.pending: dict[int, tuple[dict, float]] = {}
        self.events = queue.Queue()
        self.state = {"rope": 0, "winner": None, "players": []}
        self.role = None
        self.symbol = None
        self.running = True
        self.latencies = []
        self.last_ping = time.monotonic()
        self.voice = VoiceChat(self.sock, self.server)

    def send(self, msg, reliable=False):
        if reliable:
            msg = dict(msg, seq=self.seq)
            self.pending[self.seq] = (msg, time.monotonic())
            self.seq += 1
        self.sock.sendto(encode(msg), self.server)

    def receive_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            msg = decode(data)
            if not msg:
                continue
            if msg.get("type") == "ack":
                self.pending.pop(int(msg.get("seq", -1)), None)
            elif msg.get("type") == "pong":
                self.latencies.append(now_ms() - int(msg.get("sent", now_ms())))
            elif msg.get("type") == "registered":
                self.role, self.symbol = msg.get("role"), msg.get("symbol")
            elif msg.get("type") == "state":
                self.state = msg
            self.events.put(msg)

    def retry_loop(self):
        while self.running:
            time.sleep(0.1)
            now = time.monotonic()
            for seq, (msg, sent) in list(self.pending.items()):
                if now - sent > 0.5:
                    self.sock.sendto(encode(msg), self.server)
                    self.pending[seq] = (msg, now)
            if now - self.last_ping > 1:
                self.send({"type": "ping", "sent": now_ms()})
                self.last_ping = now

    def run(self):
        if pygame is None:
            raise SystemExit("Install dependencies first: pip install -r requirements.txt")
        pygame.init()
        screen = pygame.display.set_mode((700, 620))
        pygame.display.set_caption("UDP Tic-Tac-Toe")
        font = pygame.font.SysFont("Arial", 28)
        small = pygame.font.SysFont("Arial", 18)
        self.send({"type": "register", "name": self.name, "role": self.requested_role})
        threading.Thread(target=self.receive_loop, daemon=True).start()
        threading.Thread(target=self.retry_loop, daemon=True).start()
        clock = pygame.time.Clock()
        notice = "Connecting..."
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.send({"type": "reset"})
                    elif event.key == pygame.K_v:
                        notice = "Voice chat enabled" if self.voice.start() else "Install sounddevice for voice chat"
                    elif event.key == pygame.K_SPACE and self.role == "player" and not self.state.get("winner"):
                        self.send({"type": "pull", "amount": 1}, reliable=True)
            while not self.events.empty():
                msg = self.events.get()
                if msg.get("type") == "notice":
                    notice = msg.get("text", "")
                elif msg.get("type") == "registered":
                    notice = f"Joined as {msg.get('role')} {msg.get('symbol') or ''}"
            screen.fill((22, 24, 30))
            pygame.draw.line(screen, (180, 180, 180), (80, 300), (620, 300), 8)
            pygame.draw.line(screen, (255, 90, 90), (350, 180), (350, 420), 3)
            pygame.draw.line(screen, (255, 210, 70), (80, 180), (80, 420), 3)
            pygame.draw.line(screen, (255, 210, 70), (620, 180), (620, 420), 3)
            rope = max(-100, min(100, int(self.state.get("rope", 0))))
            x = 350 + int(2.5 * rope)
            pygame.draw.circle(screen, (245, 245, 245), (x, 300), 22)
            pygame.draw.line(screen, (245, 245, 245), (x - 20, 300), (x + 20, 300), 8)
            screen.blit(small.render("LEFT", True, (255, 120, 120)), (40, 140))
            screen.blit(small.render("RIGHT", True, (100, 180, 255)), (575, 140))
            screen.blit(small.render("Press SPACE repeatedly to pull the rope", True, (220, 220, 220)), (185, 460))
            winner = self.state.get("winner")
            title = f"{winner} PLAYER WINS!" if winner else "TUG-OF-WAR BUTTON MASHER"
            screen.blit(font.render(title, True, (255, 255, 255)), (100, 25))
            avg = sum(self.latencies[-10:]) / len(self.latencies[-10:]) if self.latencies else 0
            status = f"{notice} | role={self.role or '-'} | RTT={avg:.1f} ms | pending={len(self.pending)} | R reset, V voice"
            screen.blit(small.render(status, True, (180, 180, 180)), (20, 575))
            pygame.display.flip()
            clock.tick(60)
        self.voice.stop()
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--name", default="player")
    parser.add_argument("--spectator", action="store_true")
    args = parser.parse_args()
    Client((args.host, args.port), args.name, args.spectator).run()
