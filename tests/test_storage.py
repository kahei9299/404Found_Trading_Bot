import tempfile
import unittest

from bot.runtime.models import FillRecord, HeartbeatRecord, PositionState, SignalRecord
from bot.storage.sqlite import SQLiteStorage


class SQLiteStorageTests(unittest.TestCase):
    def test_round_trips_signal_position_and_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SQLiteStorage(f"{tmpdir}/state.sqlite3")
            storage.init_db()

            signal = SignalRecord(
                pair="BTC/USD",
                interval="1h",
                open_time=1700000000000,
                direction="LONG",
                score=6.5,
                entry=100.0,
                stop_loss=95.0,
                take_profit_1=105.0,
                take_profit_2=110.0,
                take_profit_3=115.0,
                payload={"direction": "LONG"},
            )
            storage.save_signal(signal)
            self.assertTrue(storage.has_signal("BTC/USD", "1h", 1700000000000))

            position = PositionState(
                pair="BTC/USD",
                interval="1h",
                direction="LONG",
                status="OPEN",
                entry_time=1700000001000,
                entry_price=100.0,
                quantity=1.0,
                remaining_quantity=1.0,
                stop_loss=95.0,
                take_profit_1=105.0,
                take_profit_2=110.0,
                take_profit_3=115.0,
                signal_time=1700000000000,
                fills=[FillRecord(time=1700000001000, price=100.0, quantity=1.0, reason="ENTRY")],
            )
            storage.upsert_position(position)
            loaded = storage.get_open_position("BTC/USD")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.entry_price, 100.0)
            self.assertEqual(loaded.fills[0].reason, "ENTRY")

            heartbeat = HeartbeatRecord(component="runner", status="ok", message="cycle", timestamp=1700000002000)
            storage.save_heartbeat(heartbeat)
            self.assertEqual(storage.get_last_heartbeat("runner").message, "cycle")


if __name__ == "__main__":
    unittest.main()
