"""Tests for pix2asa.cli — the standalone pix2asa command."""

from __future__ import annotations

import pytest

from pix2asa import __version__
from pix2asa.cli import main


# ---------------------------------------------------------------------------
# Minimal PIX 6 config for CLI tests
# ---------------------------------------------------------------------------

_SIMPLE = (
    "PIX Version 6.3(1)\n"
    "interface ethernet0 auto\n"
    "interface ethernet1 100full\n"
    "nameif ethernet0 outside security0\n"
    "nameif ethernet1 inside security100\n"
    "ip address outside 10.0.0.1 255.255.255.0\n"
    "ip address inside 192.168.1.1 255.255.255.0\n"
    ": end\n"
)


# ---------------------------------------------------------------------------
# --list-platforms
# ---------------------------------------------------------------------------

class TestListPlatforms:
    def test_exit_0(self, capsys):
        rc = main(["--list-platforms"])
        assert rc == 0

    def test_shows_asa_5520(self, capsys):
        main(["--list-platforms"])
        assert "asa-5520" in capsys.readouterr().out

    def test_shows_all_16_platforms(self, capsys):
        main(["--list-platforms"])
        lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
        assert len(lines) >= 16


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------

class TestVersion:
    def test_exits_0(self):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0

    def test_prints_version(self, capsys):
        with pytest.raises(SystemExit):
            main(["--version"])
        combined = capsys.readouterr()
        assert __version__ in combined.out or __version__ in combined.err


# ---------------------------------------------------------------------------
# Basic conversion
# ---------------------------------------------------------------------------

class TestConvert:
    def test_exit_0_clean_config(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        rc = main(["-f", str(f), "-t", "asa-5520"])
        assert rc == 0

    def test_output_to_stdout(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5520"])
        out = capsys.readouterr().out
        assert "ASA Version" in out

    def test_output_to_file(self, tmp_path):
        infile = tmp_path / "pix.cfg"
        outfile = tmp_path / "asa.cfg"
        infile.write_text(_SIMPLE)
        rc = main(["-f", str(infile), "-t", "asa-5520", "-o", str(outfile)])
        assert rc == 0
        assert "ASA Version" in outfile.read_text()

    def test_interface_stanza_in_output(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5520"])
        out = capsys.readouterr().out
        assert "nameif outside" in out
        assert "nameif inside" in out

    def test_pix_version_not_in_output(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5520"])
        assert "PIX Version" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

class TestFlags:
    def test_target_version_84(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5520", "-T", "84"])
        assert "ASA Version 8.4" in capsys.readouterr().out

    def test_debug_flag_emits_log(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5520", "-d"])
        out = capsys.readouterr().out
        assert "INFO:" in out

    def test_log_file_written(self, tmp_path):
        infile = tmp_path / "pix.cfg"
        logfile = tmp_path / "conv.log"
        infile.write_text(_SIMPLE)
        main(["-f", str(infile), "-t", "asa-5520", "-l", str(logfile)])
        assert logfile.exists()
        assert "INFO:" in logfile.read_text()

    def test_append_log_file(self, tmp_path):
        infile = tmp_path / "pix.cfg"
        logfile = tmp_path / "conv.log"
        logfile.write_text("EXISTING\n")
        infile.write_text(_SIMPLE)
        main(["-f", str(infile), "-t", "asa-5520", "-a", str(logfile)])
        content = logfile.read_text()
        assert content.startswith("EXISTING")
        assert "INFO:" in content

    def test_pix7_flag(self, tmp_path, capsys):
        pix7 = (
            "ASA Version 7.0(1)\n"
            "interface GigabitEthernet0/0\n"
            " nameif outside\n"
            " security-level 0\n"
            " ip address 10.0.0.1 255.255.255.0\n"
            " no shutdown\n"
            "!\n"
        )
        f = tmp_path / "pix7.cfg"
        f.write_text(pix7)
        rc = main(["-f", str(f), "-t", "asa-5520", "-7"])
        assert rc == 0

    def test_5505_flag_emits_switch_config(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f), "-t", "asa-5505", "-5"])
        out = capsys.readouterr().out
        assert "switchport access vlan" in out

    def test_map_interface(self, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        main(["-f", str(f),
              "-m", "ethernet0@GigabitEthernet0/0",
              "-m", "ethernet1@GigabitEthernet0/1"])
        out = capsys.readouterr().out
        # Output includes the mapping comment and interface stanzas
        assert "GigabitEthernet0/0" in out

    def test_boot_system_file(self, tmp_path, capsys):
        infile = tmp_path / "pix.cfg"
        bootfile = tmp_path / "boot.txt"
        infile.write_text(_SIMPLE)
        bootfile.write_text("disk0:/asa722-k8.bin\n")
        main(["-f", str(infile), "-t", "asa-5520", "-b", str(bootfile)])
        out = capsys.readouterr().out
        assert "boot system disk0:/asa722-k8.bin" in out


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_no_input_file_exits_nonzero(self):
        with pytest.raises(SystemExit):
            main(["-t", "asa-5520"])

    def test_no_platform_exits_nonzero(self, tmp_path):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        with pytest.raises(SystemExit):
            main(["-f", str(f)])

    def test_bad_map_interface_format_exits(self, tmp_path):
        f = tmp_path / "pix.cfg"
        f.write_text(_SIMPLE)
        with pytest.raises(SystemExit):
            main(["-f", str(f), "-m", "no_at_sign"])

    def test_nonexistent_input_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            main(["-f", str(tmp_path / "nonexistent.cfg"), "-t", "asa-5520"])

    def test_exit_1_on_errors(self, tmp_path):
        # Config with a failover interface used for data causes ERROR:
        config = (
            "PIX Version 6.3(5)\n"
            "nameif ethernet0 outside security0\n"
            "nameif ethernet1 inside security100\n"
            "nameif ethernet2 failover security90\n"
            "ip address outside 10.0.0.1 255.255.255.0\n"
            "failover lan interface failover ethernet2\n"
            "failover link failover ethernet2\n"
            "failover lan enable\n"
            "access-group myacl in interface failover\n"
        )
        f = tmp_path / "pix_err.cfg"
        f.write_text(config)
        rc = main(["-f", str(f), "-t", "asa-5520"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Latin-1 encoded file
# ---------------------------------------------------------------------------

class TestEncoding:
    def test_latin1_file_reads_ok(self, tmp_path, capsys):
        infile = tmp_path / "latin1.cfg"
        infile.write_bytes(
            b"PIX Version 6.3(1)\n"
            b"hostname caf\xe9-fw\n"   # 0xe9 = é in latin-1
            b"nameif ethernet0 outside security0\n"
            b"nameif ethernet1 inside security100\n"
        )
        rc = main(["-f", str(infile), "-t", "asa-5520"])
        assert rc == 0
        assert "ASA Version" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Integration: all sample configs
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSampleConfigs:
    def test_pix501(self, pix501_config, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(pix501_config)
        rc = main(["-f", str(f), "-t", "asa-5505"])
        assert rc == 0
        assert "ASA Version" in capsys.readouterr().out

    def test_pix515_fo(self, pix515_fo_config, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(pix515_fo_config)
        rc = main(["-f", str(f), "-t", "asa-5520"])
        assert "ASA Version" in capsys.readouterr().out

    def test_pix535(self, pix535_config, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(pix535_config)
        rc = main(["-f", str(f), "-t", "asa-5580-4ge"])
        assert "ASA Version" in capsys.readouterr().out

    def test_pix38(self, pix38_config, tmp_path, capsys):
        f = tmp_path / "pix.cfg"
        f.write_text(pix38_config)
        rc = main(["-f", str(f), "-t", "asa-5520"])
        assert "ASA Version" in capsys.readouterr().out
