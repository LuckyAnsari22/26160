import os

base_dir = r"d:\Downloads\26160\testbed"
os.makedirs(os.path.join(base_dir, "configs", "active"), exist_ok=True)

configs = [
    ("tunnel-aes256gcm-ecp256-pfs", "tunnel", "aes256gcm16-prfsha256-ecp256", "aes256gcm16-ecp256", False, False),
    ("tunnel-aes128cbc-sha256-modp2048-pfs", "tunnel", "aes128-sha256-modp2048", "aes128-sha256-modp2048", False, False),
    ("tunnel-aes256cbc-sha1-modp2048-nopfs", "tunnel", "aes256-sha1-modp2048", "aes256-sha1", False, False),
    ("tunnel-aes128gcm-curve25519-pfs", "tunnel", "aes128gcm16-prfsha256-curve25519", "aes128gcm16-curve25519", False, False),
    ("transport-aes256gcm-ecp256-pfs", "transport", "aes256gcm16-prfsha256-ecp256", "aes256gcm16-ecp256", False, False),
    ("transport-aes128cbc-sha256-modp2048-pfs", "transport", "aes128-sha256-modp2048", "aes128-sha256-modp2048", False, False),
    ("tunnel-weak-3des-sha1-modp1024", "tunnel", "3des-sha1-modp1024", "3des-sha1", False, False),
    ("tunnel-aes256gcm-ecp256-pfs-ipv6", "tunnel", "aes256gcm16-prfsha256-ecp256", "aes256gcm16-ecp256", True, False)
]

template = """connections {{
    testbed {{
        local_addrs = {local_ip}
        remote_addrs = {remote_ip}
        
        local {{
            auth = psk
        }}
        remote {{
            auth = psk
        }}
        
        children {{
            testbed {{
                local_ts = {local_ts}
                remote_ts = {remote_ts}
                mode = {mode}
                esp_proposals = {esp_proposal}
                rekey_time = 20m
            }}
        }}
        
        version = 2
        proposals = {ike_proposal}
        rekey_time = 60m
    }}
}}

secrets {{
    ike-psk {{
        secret = "testbed_preshared_key_2026"
    }}
}}
"""

for name, mode, ike, esp, is_ipv6, _ in configs:
    if is_ipv6:
        m_local = "fd00::1"
        m_remote = "fd00::2"
        m_l_ts = "fd01::/64" if mode == "tunnel" else "dynamic"
        m_r_ts = "fd02::/64" if mode == "tunnel" else "dynamic"
        
        s_local = "fd00::2"
        s_remote = "fd00::1"
        s_l_ts = "fd02::/64" if mode == "tunnel" else "dynamic"
        s_r_ts = "fd01::/64" if mode == "tunnel" else "dynamic"
    else:
        m_local = "10.0.0.1"
        m_remote = "10.0.0.2"
        m_l_ts = "192.168.1.0/24" if mode == "tunnel" else "dynamic"
        m_r_ts = "192.168.2.0/24" if mode == "tunnel" else "dynamic"
        
        s_local = "10.0.0.2"
        s_remote = "10.0.0.1"
        s_l_ts = "192.168.2.0/24" if mode == "tunnel" else "dynamic"
        s_r_ts = "192.168.1.0/24" if mode == "tunnel" else "dynamic"

    moon_content = template.format(local_ip=m_local, remote_ip=m_remote, local_ts=m_l_ts, remote_ts=m_r_ts, mode=mode, esp_proposal=esp, ike_proposal=ike)
    sun_content = template.format(local_ip=s_local, remote_ip=s_remote, local_ts=s_l_ts, remote_ts=s_r_ts, mode=mode, esp_proposal=esp, ike_proposal=ike)
    
    with open(os.path.join(base_dir, "configs", f"{name}-moon.conf"), "w") as f:
        f.write(moon_content)
    with open(os.path.join(base_dir, "configs", f"{name}-sun.conf"), "w") as f:
        f.write(sun_content)

print("Configs generated!")
