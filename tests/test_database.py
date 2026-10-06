import textwrap

from minipro_gui.database import ChipDatabase, pin_count

SAMPLE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <infoic>
      <database type="INFOIC2PLUS">
        <manufacturer name="Winbond">
          <ic name="W25Q32BV,W25Q32BV@SOIC8" type="1" protocol_id="0x03" chip_id="0x00ef4016"
              code_memory_size="0x400000" data_memory_size="0x00" package_details="0x08000900"/>
          <ic name="W25Q32BV@SOIC16" type="1" protocol_id="0x03" chip_id="0x00ef4016"
              code_memory_size="0x400000" data_memory_size="0x00" package_details="0x10000900"/>
          <ic name="AT28C256" type="1" protocol_id="0x07" chip_id="0x00000000"
              code_memory_size="0x8000" data_memory_size="0x00" package_details="0x1c000000"/>
          <ic name="PIC16F84A" type="2" protocol_id="0x63" chip_id="0x00000560"
              code_memory_size="0x800" data_memory_size="0x40" package_details="0x12000000"/>
        </manufacturer>
        <custom name="Mine">
          <ic name="MYCHIP" type="1" protocol_id="0x07" chip_id="0x0" code_memory_size="0x100"
              data_memory_size="0x0" package_details="0x18000000"/>
        </custom>
      </database>
      <database type="INFOIC">
        <manufacturer name="Atmel">
          <ic name="AT28C256" type="1" protocol_id="0x07" chip_id="0x0" code_memory_size="0x8000"
              data_memory_size="0x0" package_details="0x1c000000"/>
        </manufacturer>
      </database>
    </infoic>
""")


def load(tmp_path):
    path = tmp_path / "infoic.xml"
    path.write_text(SAMPLE)
    return ChipDatabase.load(str(path))


def test_pin_count_handles_plcc_adapters():
    assert pin_count(0x1C000000) == 28
    assert pin_count(0x3F000000) == 32


def test_lookup_by_name(tmp_path):
    db = load(tmp_path)
    rec = db.get("tl866ii", "AT28C256")
    assert rec.code_size == 0x8000 and rec.pins == 28
    assert db.get("t48", "W25Q32BV@SOIC8").pins == 8
    assert db.get("tl866a", "AT28C256") is not None
    assert db.get("tl866a", "W25Q32BV") is None
    assert db.get("tl866ii", "MYCHIP(custom)").custom


def test_logic_ics(tmp_path):
    infoic = tmp_path / "infoic.xml"
    infoic.write_text(SAMPLE)
    logic = tmp_path / "logicic.xml"
    logic.write_text('<logicic><database type="LOGIC"><manufacturer name="Logic Ic">'
                     '<ic name="7400,7437" type="5" voltage="5V" pins="14"><vector id="00"> 0 </vector></ic>'
                     '</manufacturer></database></logicic>')
    db = ChipDatabase.load(str(infoic), str(logic))
    assert db.get("tl866a", "7437").chip_type == 5
    assert db.get("t48", "7400").pins == 14


def test_find_by_chip_id(tmp_path):
    db = load(tmp_path)
    names = [r.name for r in db.find_by_chip_id("tl866ii", 0xEF4016)]
    assert names == ["W25Q32BV", "W25Q32BV@SOIC8", "W25Q32BV@SOIC16"]
    names = [r.name for r in db.find_by_chip_id("tl866ii", 0xEF4016, pins=16)]
    assert names == ["W25Q32BV@SOIC16"]
    # revision bits stripped (ID type 3)
    assert [r.name for r in db.find_by_chip_id("tl866ii", 0x560 >> 5)] == ["PIC16F84A"]
    assert db.find_by_chip_id("tl866ii", 0x123456) == []
