import pandas as pd
import numpy as np
import os

os.makedirs("data", exist_ok=True)

# Set random seed for reproducibility
np.random.seed(42)

def generate_synthetic_features(num_samples_per_class=50):
    classes = ["voip", "video", "web", "icmp", "bulk", "email"]
    configs = [
        "tunnel-aes256gcm-ecp256-pfs",
        "tunnel-aes128cbc-sha256-modp2048-pfs",
        "tunnel-aes256cbc-sha1-modp2048-nopfs"
    ]
    
    data = []
    
    for cls in classes:
        for _ in range(num_samples_per_class):
            config = np.random.choice(configs)
            flow_id = f"192.168.1.10_192.168.2.10_0x{np.random.randint(1000, 9999)}"
            
            # Base features
            direction_ratio = np.random.uniform(0.4, 0.6)
            
            if cls == "voip":
                # VoIP: Highly periodic, small variance, exactly ~160 byte payloads + IPsec overhead
                pkt_count = int(np.random.normal(500, 50))
                mean_len = np.random.normal(210, 5) # 160 + ESP overhead
                std_len = np.random.uniform(0, 10)  # Very low variance
                mean_iat = np.random.normal(0.02, 0.002) # ~20ms
                std_iat = np.random.uniform(0.001, 0.005)
                max_len = mean_len + 20
                min_len = mean_len - 20
                
            elif cls == "video":
                # Video: Large packets, bursty IAT
                pkt_count = int(np.random.normal(3000, 500))
                mean_len = np.random.normal(1200, 100)
                std_len = np.random.uniform(300, 500) # High variance due to frame sizes
                mean_iat = np.random.normal(0.005, 0.001)
                std_iat = np.random.uniform(0.01, 0.05) # High IAT variance
                max_len = 1360 # MTU cap
                min_len = 64
                
            elif cls == "web":
                # Web: Bimodal (small requests, large responses)
                pkt_count = int(np.random.normal(200, 50))
                direction_ratio = np.random.uniform(0.1, 0.3) # mostly download
                mean_len = np.random.normal(800, 200)
                std_len = np.random.uniform(400, 600)
                mean_iat = np.random.normal(0.1, 0.05)
                std_iat = np.random.uniform(0.1, 0.5)
                max_len = 1360
                min_len = 64
                
            elif cls == "icmp":
                # ICMP: Exactly 1000ms IAT, small standard size
                pkt_count = int(np.random.normal(30, 2))
                mean_len = np.random.normal(120, 2)
                std_len = 0.0
                mean_iat = np.random.normal(1.0, 0.001)
                std_iat = 0.0001
                max_len = mean_len
                min_len = mean_len
                
            elif cls == "bulk":
                # Bulk (Iperf TCP): Max length, minimal IAT
                pkt_count = int(np.random.normal(5000, 1000))
                mean_len = np.random.normal(1300, 50)
                std_len = np.random.uniform(10, 50)
                mean_iat = np.random.normal(0.001, 0.0005)
                std_iat = np.random.uniform(0.0001, 0.001)
                max_len = 1360
                min_len = 64
                
            elif cls == "email":
                # Email (SMTP): short bursts
                pkt_count = int(np.random.normal(50, 10))
                mean_len = np.random.normal(400, 100)
                std_len = np.random.uniform(200, 300)
                mean_iat = np.random.normal(0.5, 0.2)
                std_iat = np.random.uniform(0.1, 0.5)
                max_len = 1000
                min_len = 64
                
            # Filter simulated flows < 20 pkts (our floor logic)
            if pkt_count < 20:
                continue
                
            max_iat = mean_iat + (std_iat * 3)
            flow_duration = pkt_count * mean_iat
            
            data.append({
                "flow_id": flow_id,
                "config": config,
                "label": cls,
                "pkt_count": pkt_count,
                "direction_ratio": round(direction_ratio, 2),
                "mean_len": round(mean_len, 2),
                "std_len": round(std_len, 2),
                "max_len": round(max_len, 2),
                "min_len": round(min_len, 2),
                "mean_iat": round(mean_iat, 5),
                "std_iat": round(std_iat, 5),
                "max_iat": round(max_iat, 5),
                "flow_duration": round(flow_duration, 2)
            })
            
    df = pd.DataFrame(data)
    df.to_csv("data/features.csv", index=False)
    print(f"Generated {len(df)} synthetic flows safely simulating PCAP extraction.")

if __name__ == "__main__":
    generate_synthetic_features()
