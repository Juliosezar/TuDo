"""Helpers for gathering local network information (Linux)."""

import os
import socket
import struct

# fcntl is a standard built-in module on Linux systems
try:
    import fcntl
except ImportError:
    fcntl = None


def get_network_ips() -> list[tuple[str, str]]:
    results = []

    # ------------------ 1. Fetch IPv4 Addresses ------------------
    interfaces = []
    try:
        with open("/proc/net/dev", "r") as f:
            for line in f.readlines()[2:]:  # Skip headers
                parts = line.split(":")
                if len(parts) > 1:
                    ifname = parts[0].strip()
                    if ifname != "lo":
                        interfaces.append(ifname)
    except Exception:
        pass

    if fcntl:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for ifname in interfaces:
            try:
                ip = socket.inet_ntoa(
                    fcntl.ioctl(
                        s.fileno(),
                        0x8915,
                        struct.pack("256s", ifname[:15].encode("utf-8")),
                    )[20:24]
                )

                # Ignore IPs starting with 172. (usually docker/virtual bridges)
                if not ip.startswith("172."):
                    results.append((ifname, ip))

            except OSError:
                continue

    # ------------------ 2. Fetch IPv6 Addresses ------------------
    # On Linux, /proc/net/if_inet6 lists active IPv6 interfaces
    if os.path.exists("/proc/net/if_inet6"):
        try:
            with open("/proc/net/if_inet6", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 6:
                        # Format is: [32-char hex IP] [iface index] [prefix len] [scope] [flags] [ifname]
                        hex_addr, _, _, _, _, ifname = parts
                        if ifname != "lo":
                            try:
                                # Convert the 32-char hex string back to a 16-byte raw object
                                raw_bytes = bytes.fromhex(hex_addr)
                                # Convert to the canonical IPv6 representation (e.g. "fe80::...")
                                ipv6_str = socket.inet_ntop(socket.AF_INET6, raw_bytes)
                                results.append((ifname, ipv6_str))
                            except Exception:
                                continue
        except Exception:
            pass

    return results
