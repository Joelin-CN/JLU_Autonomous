from chaoxing.api import _make_protocol_handler


class FakeProtocol:
    def __init__(self):
        self.events = []

    def emit_progress(self, percent, message, account_id=None, lane_status=None):
        self.events.append(("PROGRESS", percent, message, account_id, lane_status))

    def emit_log(self, level, message):
        self.events.append(("LOG", level, message))

    def emit_phase(self, phase):
        self.events.append(("PHASE", phase))

    def emit_ticket(self, ticket):
        self.events.append(("TICKET", ticket))

    def emit_memory(self, payload):
        self.events.append(("MEMORY", payload))


def test_protocol_handler_forwards_account_id_and_lane_status():
    fp = FakeProtocol()
    handler = _make_protocol_handler(fp)
    handler({"type": "PROGRESS", "percent": 40, "message": "Queued",
             "accountId": 2, "laneStatus": "queued"})
    assert fp.events[0][0] == "PROGRESS"
    assert fp.events[0][3] == 2
    assert fp.events[0][4] == "queued"


def test_protocol_handler_forwards_memory():
    fp = FakeProtocol()
    handler = _make_protocol_handler(fp)
    payload = {"type": "MEMORY", "budgetGB": 12.9, "projectChromeGB": 1.1}
    handler(payload)
    assert fp.events[0] == ("MEMORY", payload)


def test_ram_guard_override_thresholds(monkeypatch):
    from chaoxing import logging_setup as ls
    ls.set_ram_limit_gb(14.0)
    assert ls._ram_thresholds() == (12.0, 13.0, 14.0)
    ls.set_ram_limit_gb(None)
    assert ls._ram_thresholds() == (20.0, 22.0, 24.0)
