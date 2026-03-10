"""Rule tables and dispatcher factory for the PIX-to-ASA converter.

Contains:
  - RULES_COMMON: shared rules for both PIX 6 and PIX 7
  - RULES_V6: PIX OS 6.x specific rules
  - RULES_V7: PIX OS 7.x specific rules (interface renaming only)
  - _pppoe_rules(): version-dependent PPPoE address rules
  - build_dispatcher(): assembles the correct rule set for a conversion pass
"""

from __future__ import annotations

from ..context import ConversionContext
from ..engine import Dispatcher, Rule, _r
from ..models import SourceVersion

from .conduit import _handle_conduit
from .failover import (
    _handle_failover_lan_interface,
    _handle_failover_lan_key,
    _handle_failover_lan_rename,
    _handle_failover_link,
    _handle_failover_link_rename,
    _handle_failover_poll,
)
from .inspect import (
    _handle_fixup,
    _handle_fixup_dns,
    _handle_fixup_dns_neg,
    _handle_fixup_esp_ike,
    _handle_fixup_generic,
    _handle_fixup_generic_neg,
    _handle_fixup_h323_bare,
    _handle_fixup_h323_bare_neg,
    _handle_fixup_neg,
)
from .interfaces import (
    _handle_allocate_interface,
    _handle_interface,
    _handle_interface_rename_only,
    _handle_ip_dhcp,
    _handle_ip_pppoe,
    _handle_ip_static,
    _handle_logical_interface,
    _handle_mtu,
    _handle_nameif,
    _handle_nameif_logical,
    _handle_no_ip_address,
    _handle_standby_ip,
    _handle_vlan_interface_rename,
    setup_custom_if,
)
from .misc import (
    _conduit_not_supported,
    _handle_asdm_history,
    _handle_asdm_location,
    _handle_asdm_logging,
    _handle_hostname,
    _handle_sysopt_permit_ipsec,
    _handle_vpdn_group,
    _ignore,
    _isakmp_blanked,
    _not_supported,
    _password_blanked,
    _repeat,
)
from .names import _handle_name
from .nat import (
    _handle_access_group,
    _handle_access_list,
    _handle_global,
    _handle_nat,
    _handle_pix_port_redirect,
    _handle_pix_static,
    _handle_route,
)


# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------
# Pattern conventions:
#   - All patterns compiled with re.IGNORECASE via _r()
#   - Named groups used throughout (?P<name>...)
#   - keyword = first CLI token, lower-cased

# Rules shared across PIX 6 and PIX 7
RULES_COMMON: list[Rule] = [
    Rule("pix",       _r(r"PIX\s+Version\s+\S*"),              _ignore),
    Rule("",          _r(r"Cryptochecksum:\S*"),               _ignore),
    Rule("",          _r(r"\[OK\]|:\s*end"),                    _ignore),
    # hostname — shared across all PIX versions
    Rule("hostname",  _r(r"hostname\s+(?P<name>\S+)"),          _handle_hostname),
    # PIX 'name' command → ASA host object
    # name <ip> <hostname> [description <text>]
    Rule("name",      _r(r"name\s+(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+(?P<name>\S+)"
                         r"(?:\s+description\s+(?P<desc>.+))?"),
         _handle_name),
    # access-list: inject 'extended', substitute host refs → object refs
    Rule("access-list", _r(r"access-list\s+.*"), _handle_access_list),
    # PIX port-redirect static NAT → ASA object NAT with service redirect (MUST precede ip-only static rule)
    # static (<src_if>,<dst_if>) tcp|udp <ext_addr|interface> <ext_port> <int_ip> <int_port> ...
    Rule("static", _r(r"static\s+\((?P<src_if>\S+),(?P<dst_if>\S+)\)\s+"
                       r"(?P<proto>tcp|udp)\s+"
                       r"(?P<ext_addr>interface|\d{1,3}(?:\.\d{1,3}){3})\s+"
                       r"(?P<ext_port>\S+)\s+"
                       r"(?P<int_ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
                       r"(?P<int_port>\S+)"),
         _handle_pix_port_redirect),
    # PIX static NAT → ASA object-based NAT (IP-to-IP or name-to-IP or name-to-name)
    # static (<src_if>,<dst_if>) <mapped_ip|name> <real_ip|name> netmask <mask_ip>
    Rule("static", _r(r"static\s+\((?P<src_if>\S+),(?P<dst_if>\S+)\)\s+"
                       r"(?P<mapped>\S+)\s+"
                       r"(?P<real>\S+)\s+"
                       r"netmask\s+(?P<mask>\d{1,3}(?:\.\d{1,3}){3}).*"),
         _handle_pix_static),
]

# PIX OS 6.x rules
RULES_V6: list[Rule] = [
    # --- interface declarations ---
    Rule("interface", _r(
        r"interface\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)\s+vlan(?P<vlan>\d+)\s+logical\s+(?P<state>shutdown)"),
         _handle_logical_interface),
    Rule("interface", _r(
        r"interface\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)\s+vlan(?P<vlan>\d+)\s+logical"),
         _handle_logical_interface),
    Rule("interface", _r(
        r"interface\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)\s+"
        r"(?P<speed>aui|auto|bnc10baset|10full|100basetx|100full|1000auto|1000full\s+nonegotiate|1000full)"
        r"\s+(?P<state>shutdown)"),
         _handle_interface),
    Rule("interface", _r(
        r"interface\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)\s+"
        r"(?P<speed>aui|auto|bnc10baset|10full|100basetx|100full|1000auto|1000full\s+nonegotiate|1000full)"),
         _handle_interface),
    Rule("interface", _r(r"interface\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)"), _handle_interface),

    # --- nameif ---
    Rule("nameif", _r(
        r"nameif\s+(?P<hw>[eEgG][\-a-zA-Z]+\d)\s+(?P<name>[a-zA-Z][a-zA-Z\-_/0-9]*)\s+security(?P<level>\d+)"),
         _handle_nameif),
    Rule("nameif", _r(
        r"nameif\s+(?P<hw>vlan\d+)\s+(?P<name>[a-zA-Z][a-zA-Z_/0-9]*)\s+security(?P<level>\d+)"),
         _handle_nameif_logical),

    # --- data-plane commands (nameif-based) ---
    Rule("nat",          _r(r"nat\s+\((?P<nameif>\S+)\)\s+.*"),          _handle_nat),
    Rule("route",        _r(r"route\s+(?P<nameif>\S+)\s+.*"),             _handle_route),
    Rule("global",       _r(r"global\s+\((?P<nameif>\S+)\)\s+.*"),       _handle_global),
    Rule("access-group", _r(r"access-group\s+\S+\s+(?:in|out)\s+interface\s+(?P<nameif>\S+)"),
         _handle_access_group),
    Rule("mtu",          _r(r"mtu\s+(?P<nameif>[a-zA-Z][a-zA-Z_/0-9]*)\s+(?P<mtu>\d+)"),
         _handle_mtu),

    # --- ip address ---
    Rule("ip", _r(
        r"ip\s+address\s+(?P<nameif>\S+)\s+"
        r"(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
        r"(?P<mask>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"),
         _handle_ip_static),
    Rule("ip", _r(r"ip\s+address\s+(?P<nameif>\S+)\s+dhcp\s+(?P<setroute>setroute)"),
         _handle_ip_dhcp),
    Rule("ip", _r(r"ip\s+address\s+(?P<nameif>\S+)\s+dhcp"), _handle_ip_dhcp),
    Rule("ip", _r(r"no\s+ip\s+address"), _handle_no_ip_address),

    # --- failover ip address (PIX6 standby) ---
    Rule("failover", _r(
        r"failover\s+ip\s+address\s+(?P<nameif>\S+)\s+"
        r"(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"),
         _handle_standby_ip),
    Rule("failover", _r(r"failover\s+lan\s+key\s+\*{8}"),        _handle_failover_lan_key),
    Rule("failover", _r(r"failover\s+lan\s+enable"),              _not_supported),
    Rule("failover", _r(r"failover\s+lan\s+interface\s+(?P<nameif>\S+)"),
         _handle_failover_lan_interface),
    Rule("failover", _r(r"failover\s+link\s+(?P<nameif>\S+)"),   _handle_failover_link),
    Rule("failover", _r(r"failover\s+poll\s+(?P<time>\d+)"),     _handle_failover_poll),

    # --- fixup / inspect ---
    # esp-ike → ipsec-pass-thru
    Rule("fixup",    _r(r"fixup\s+protocol\s+esp-ike$"),          _handle_fixup_esp_ike),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+esp-ike$"),     _handle_fixup_esp_ike),

    # dns (special: carries maximum-length)
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>dns)\s+maximum-length\s+(?P<port>\d+)"),
         _handle_fixup_dns),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>dns)\s+maximum-length\s+(?P<port>\d+)"),
         _handle_fixup_dns_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>dns)$"),   _handle_fixup_dns),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>dns)$"), _handle_fixup_dns_neg),

    # smtp (renamed to esmtp inside handler)
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>smtp)\s+(?P<port>25)"),     _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>smtp)\s+(?P<port>25)"),_handle_fixup_neg),

    # h323 subtypes — qualified first (more specific), then bare h323
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>h323\s+ras)\s+(?P<port>1718-1719)"),   _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>h323\s+ras)\s+(?P<port>1718-1719)"),_handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>h323\s+h225)\s+(?P<port>1720)\b"),      _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>h323\s+h225)\s+(?P<port>1720)\b"), _handle_fixup_neg),
    # bare 'h323 <port>' — emits both h225 and ras inspect entries
    Rule("fixup",    _r(r"fixup\s+protocol\s+h323\s+(?P<port>[\d-]+)"),   _handle_fixup_h323_bare),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+h323\s+(?P<port>[\d-]+)"), _handle_fixup_h323_bare_neg),

    # generic fixup protocol <name> <port>
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>ftp\s+strict)\s+(?P<port>21)"),   _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>ftp\s+strict)\s+(?P<port>21)"),_handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>ftp)\s+(?P<port>21)"),             _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>ftp)\s+(?P<port>21)"),       _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>http)\s+(?P<port>80)"),            _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>http)\s+(?P<port>80)"),      _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>ils)\s+(?P<port>389)"),            _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>ils)\s+(?P<port>389)"),      _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>rsh)\s+(?P<port>514)"),            _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>rsh)\s+(?P<port>514)"),      _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>rtsp)\s+(?P<port>554)"),           _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>rtsp)\s+(?P<port>554)"),     _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>snmp)\s+(?P<port>161-162)"),       _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>snmp)\s+(?P<port>161-162)"), _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>sip)\s+(?P<port>5060)"),           _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>sip)\s+(?P<port>5060)"),     _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>sip)\s+(?P<port>udp\s+5060)"),    _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>sip)\s+(?P<port>udp\s+5060)"),_handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>skinny)\s+(?P<port>2000)"),        _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>skinny)\s+(?P<port>2000)"),  _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>sqlnet)\s+(?P<port>1521)"),        _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>sqlnet)\s+(?P<port>1521)"),  _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>tftp)\s+(?P<port>69)"),            _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>tftp)\s+(?P<port>69)"),      _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>ctiqbe)\s+(?P<port>2748)"),        _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>ctiqbe)\s+(?P<port>2748)"),  _handle_fixup_neg),
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>pptp)\s+(?P<port>1723)"),          _handle_fixup),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>pptp)\s+(?P<port>1723)"),    _handle_fixup_neg),
    # generic catch-all: fixup with non-default port or less common protocol
    Rule("fixup",    _r(r"fixup\s+protocol\s+(?P<proto>\S+)\s+(?P<port>\S+)"),           _handle_fixup_generic),
    Rule("no",       _r(r"no\s+fixup\s+protocol\s+(?P<proto>\S+)\s+(?P<port>\S+)"),     _handle_fixup_generic_neg),

    # sysopt
    Rule("sysopt",   _r(r"sysopt\s+connection\s+permit-ipsec"),   _handle_sysopt_permit_ipsec),
    Rule("sysopt",   _r(r"sysopt\s+connection\s+permit-pptp"),    _not_supported),
    Rule("no",       _r(r"no\s+sysopt\s+route\s+dnat"),           _not_supported),
    Rule("sysopt",   _r(r"sysopt\s+route\s+dnat"),                _not_supported),

    # VPDN
    Rule("vpnclient", _r(r"vpnclient\s+vpngroup\s+\S+\s+password\s+\*{8}"), _password_blanked),
    Rule("vpnclient", _r(r"vpnclient\s+username\s+\S+\s+password\s+\*{8}"), _password_blanked),
    Rule("vpdn",      _r(r"vpdn\s+username\s+\S+\s+password\s+\*{9}"),      _password_blanked),
    Rule("vpdn",      _r(r"vpdn\s+group\s+(?P<group>\S+)\s+request\s+dialout\s+pppoe"),
         _handle_vpdn_group),
    Rule("vpdn",      _r(r"vpdn\s+group\s+\S+\s+ppp\s+authentication\s+(?:pap|chap|mschap)"), _repeat),
    Rule("vpdn",      _r(r"vpdn\s+group\s+\S+\s+localname\s+\S+"),          _repeat),
    Rule("vpdn",      _r(r"vpdn\s+group\s+"),                                _not_supported),
    Rule("vpdn",      _r(r"vpdn\s+enable"),                                  _not_supported),

    # PDM → ASDM
    Rule("pdm",  _r(r"pdm\s+logging\s+(?P<level>\S+)\s+(?P<msgs>\S+)"),     _handle_asdm_logging),
    Rule("pdm",  _r(r"pdm\s+logging\s+(?P<level>\S+)"),                     _handle_asdm_logging),
    Rule("pdm",  _r(r"pdm\s+logging"),                                       _handle_asdm_logging),
    Rule("pdm",  _r(r"pdm\s+location\s+(?P<ip>\S+)\s+(?P<mask>\S+)\s+(?P<nameif>\S+)"),
         _handle_asdm_location),
    Rule("pdm",  _r(r"pdm\s+history\s+enable"),                              _handle_asdm_history),

    # conduit / apply / outbound
    Rule("conduit",  _r(r"conduit\s+(?:permit|deny)\s+\S+\s+.*"),  _handle_conduit),
    Rule("conduit",  _r(r"conduit"),                                 _conduit_not_supported),
    Rule("apply",    _r(r"apply"),     _conduit_not_supported),
    Rule("outbound", _r(r"outbound"),  _conduit_not_supported),

    # passwords / keys
    Rule("isakmp",      _r(r"isakmp\s+key\s+\*{8}"),  _isakmp_blanked),

    # misc
    Rule("floodguard",  _r(r"floodguard\s+enable"),   _not_supported),
]


# PPPoE rules — version-dependent
def _pppoe_rules(supported: bool) -> list[Rule]:
    """Return the two PPPoE address rules, using the real handler or _not_supported based on supported."""
    handler = _handle_ip_pppoe if supported else _not_supported
    return [
        Rule("ip", _r(r"ip\s+address\s+(?P<nameif>\S+)\s+pppoe\s+(?P<setroute>setroute)"), handler),
        Rule("ip", _r(r"ip\s+address\s+(?P<nameif>\S+)\s+pppoe"), handler),
    ]


# PIX OS 7.x rules (interface renaming only — config is already in ASA-like syntax)
RULES_V7: list[Rule] = [
    Rule("interface", _r(r"interface\s+(?P<hw>[eg][a-z]+\d)\.(?P<sub>\d+)"),  _handle_interface_rename_only),
    Rule("interface", _r(r"interface\s+(?P<hw>[eg][a-z]+\d)"),                _handle_interface_rename_only),
    Rule("interface", _r(r"interface\s+(?P<vlan>vlan\d+)"),                   _handle_vlan_interface_rename),
    # allocate-interface (context mode)
    Rule("",          _r(r"\s+allocate-interface\s+(?P<hw>[eEgG][a-zA-Z]+\d)(?P<sub>\.\d+)?"),
         _handle_allocate_interface),
    # failover renaming
    Rule("failover",  _r(r"failover\s+link\s+(?P<nameif>\S+)\s+(?P<hw>\S+)\.(?P<sub>\d+)"),
         _handle_failover_link_rename),
    Rule("failover",  _r(r"failover\s+link\s+(?P<nameif>\S+)\s+(?P<hw>\S+)"),
         _handle_failover_link_rename),
    Rule("failover",  _r(r"failover\s+lan\s+interface\s+(?P<nameif>\S+)\s+(?P<hw>\S+)\.(?P<sub>\d+)"),
         _handle_failover_lan_rename),
    Rule("failover",  _r(r"failover\s+lan\s+interface\s+(?P<nameif>\S+)\s+(?P<hw>\S+)"),
         _handle_failover_lan_rename),
]


# ---------------------------------------------------------------------------
# Dispatcher factory
# ---------------------------------------------------------------------------

def build_dispatcher(ctx: ConversionContext) -> Dispatcher:
    """Assemble the correct rule set for this conversion pass."""
    rules: list[Rule] = list(RULES_COMMON)

    if ctx.source_version == SourceVersion.PIX6:
        rules.extend(RULES_V6)
        rules.extend(_pppoe_rules(supported=True))
    else:
        rules.extend(RULES_V7)

    return Dispatcher(rules)
