from minipro_gui import minipro
from minipro_gui.minipro import Operation, OutputParser, ProgramOptions, build_args


def test_parse_version():
    text = "minipro version 0.7.4     A free and open TL866 series programmer\nShare dir:\t/opt/x/share/minipro\n"
    info = minipro.parse_version(text)
    assert info.version == "0.7.4"
    assert info.share_dir == "/opt/x/share/minipro"


def test_parse_presence():
    assert minipro.parse_presence("tl866ii: TL866II+\n").key == "tl866ii"
    assert minipro.parse_presence("tl866a: TL866CS").model == "TL866CS"
    status = minipro.parse_presence("[No programmer found]\n")
    assert not status.connected


def test_parse_device_info_and_size():
    info = minipro.parse_device_info("Name: AT28C256\nMemory: 32768 Bytes\nPackage: DIP28\n")
    assert info["Package"] == "DIP28"
    assert minipro.parse_size(info["Memory"]) == 32768
    assert minipro.parse_size("1024 Words") == 2048


def test_build_write_defaults():
    assert build_args(Operation.WRITE, "AT28C256", "rom.bin") == ["-p", "AT28C256", "-w", "rom.bin"]


def test_build_write_with_options():
    opts = ProgramOptions(skip_erase=True, allow_size_mismatch=True, vpp="12.5", memory="code", icsp="vcc")
    args = build_args(Operation.WRITE, "27C256", "a b.bin", opts)
    assert args[:3] == ["-p", "27C256", "-i"]
    assert ["-c", "code"] == args[args.index("-c"):args.index("-c") + 2]
    assert "-e" in args and "-s" in args and "--vpp=12.5" in args
    assert args[args.index("-w") + 1] == "a b.bin"


def test_build_other_operations():
    assert build_args(Operation.READ, "X", "o.hex", ProgramOptions(file_format="ihex"))[-2:] == ["-f", "ihex"]
    assert build_args(Operation.VERIFY, "X", "f")[-2:] == ["-m", "f"]
    assert build_args(Operation.BLANK, "X") == ["-p", "X", "-b"]
    assert build_args(Operation.ERASE, "X", options=ProgramOptions(memory="code")) == ["-p", "X", "-E"]
    assert build_args(Operation.PIN_CHECK, "X") == ["-p", "X", "-z"]
    assert build_args(Operation.READ_ID, "X") == ["-p", "X", "-D"]
    assert build_args(Operation.LOGIC_TEST, "7400", options=ProgramOptions(vcc="3.3")) == \
        ["-p", "7400", "-T", "--vcc=3.3"]


def test_build_requires_file():
    import pytest

    with pytest.raises(ValueError):
        build_args(Operation.WRITE, "X")


def test_options_roundtrip_only_stores_non_defaults():
    opts = ProgramOptions(skip_verify=True, vcc="5")
    data = opts.to_dict()
    assert data == {"skip_verify": True, "vcc": "5"}
    assert ProgramOptions.from_dict({**data, "bogus": 1}) == opts


def test_output_parser_progress_and_lines():
    p = OutputParser()
    events = p.feed("Found TL866II+ 04.2.132 (0x284)\n\r\x1b[KWriting Code...  ")
    assert events[0] == ("line", "Found TL866II+ 04.2.132 (0x284)")
    events = p.feed("\r\x1b[KWriting Code...  42%")
    assert ("progress", ("Writing Code...", 42)) in events
    events = p.feed("\r\x1b[KWriting Code...  1.20Sec  OK\n")
    assert events[-1] == ("line", "Writing Code...  1.20Sec  OK")


def test_parse_chip_id():
    r = minipro.parse_chip_id("Chip ID: 0xEF4016  OK\n")
    assert r.status == "match" and r.chip_id == 0xEF4016
    r = minipro.parse_chip_id("Chip ID mismatch: expected 0x00C22016, got 0xEF4016 (W25Q32@MLP8)\n")
    assert r.status == "mismatch" and r.chip_id == 0xEF4016 and r.expected == 0xC22016
    assert r.minipro_guess == "W25Q32@MLP8"
    r = minipro.parse_chip_id("Chip ID mismatch: expected 0x1234, got 0xFFFF (unknown)\n")
    assert r.minipro_guess is None
    assert minipro.parse_chip_id("This chip doesn't have a chip ID!\n").status == "no_id"
    assert minipro.parse_chip_id("No programmer found.\n").status == "error"


def test_parse_autodetect():
    r = minipro.parse_autodetect("W25Q32BV\nW25Q32FV\n", "Autodetecting device (ID:0xEF4016)\n2 device(s) found.\n")
    assert r.chip_id == 0xEF4016 and r.devices == ["W25Q32BV", "W25Q32FV"]


def test_last_meaningful_line():
    text = "Found TL866II+\nWriting Code...  OK\nVerification failed at address 0x0042: File=0x12, Device=0xFF\n"
    assert minipro.last_meaningful_line(text).startswith("Verification failed")
