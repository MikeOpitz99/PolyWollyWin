import importlib
import sys
import types
import unittest


class FakeDevice:
    def __init__(self, *, write_result=1025, write_error=None, open_error=None):
        self.write_result = write_result
        self.write_error = write_error
        self.open_error = open_error
        self.opened_path = None
        self.closed = False
        self.last_write = None

    def open_path(self, path):
        if self.open_error:
            raise self.open_error
        self.opened_path = path

    def write(self, data):
        self.last_write = data
        if self.write_error:
            raise self.write_error
        return self.write_result

    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.devices = []
        self.enumerated = [
            {
                "usage_page": 0xFF02,
                "path": b"matrix-path",
                "interface_number": 4,
            }
        ]
        fake_hid = types.ModuleType("hid")
        fake_hid.enumerate = lambda vid, pid: list(self.enumerated)
        fake_hid.device = self._make_device
        sys.modules["hid"] = fake_hid
        sys.modules.pop("transport", None)
        self.transport_module = importlib.import_module("transport")

    def tearDown(self):
        sys.modules.pop("transport", None)
        sys.modules.pop("hid", None)

    def _make_device(self):
        device = FakeDevice()
        self.devices.append(device)
        return device

    def test_connect_opens_matrix_usage_page(self):
        transport = self.transport_module.Transport()

        path = transport.connect()

        self.assertEqual(path, "matrix-path")
        self.assertTrue(transport.connected)
        self.assertEqual(self.devices[0].opened_path, b"matrix-path")

    def test_frame_write_uses_report_id_and_full_payload(self):
        transport = self.transport_module.Transport()
        transport.connect()

        written = transport.send_frame([7] * 312)

        packet = self.devices[0].last_write
        self.assertEqual(written, 1025)
        self.assertEqual(len(packet), 1025)
        self.assertEqual(packet[:5], [0x00, 0x60, 0x81, 0x00, 0x00])
        self.assertEqual(packet[5:317], [7] * 312)

    def test_failed_write_closes_and_invalidates_stale_handle(self):
        transport = self.transport_module.Transport()
        transport.connect()
        device = self.devices[0]
        device.write_error = OSError("device disappeared")

        with self.assertRaisesRegex(RuntimeError, "connection was invalidated"):
            transport.send_blank()

        self.assertTrue(device.closed)
        self.assertFalse(transport.connected)

    def test_nonpositive_write_invalidates_handle(self):
        transport = self.transport_module.Transport()
        transport.connect()
        device = self.devices[0]
        device.write_result = -1

        with self.assertRaisesRegex(RuntimeError, "returned no data"):
            transport.send_blank()

        self.assertTrue(device.closed)
        self.assertFalse(transport.connected)


if __name__ == "__main__":
    unittest.main()
