import pandas as pd
import numpy as np
import os

# Set random seed for reproducibility
np.random.seed(99)

def generate_iscx_features(num_samples_per_class=20):
    """
    Simulates features extracted from the ISCXVPN2016 dataset.
    Crucially, these features include WAN jitter and GRO/TSO artifacts,
    meaning standard deviations (std_iat, std_len) will be shifted compared
    to the pristine lab data in features.csv. This forces the model to prove
    it learned robust thresholds, not just overfit to lab latency.
    """
    classes = ["voip", "video", "web", "icmp", "bulk", "email"]
    configs = ["iscx-replay"]
    
    data = []
    
    for cls in classes:
        for _ in range(num_samples_per_class):
            config = "iscx-replay"
            flow_id = f"131.202.x.x_192.168.1.10_0x{np.random.randint(1000, 9999)}"
            
            # Base features - WAN introduces asymmetric routing sometimes, shifting ratios
            direction_ratio = np.random.uniform(0.3, 0.7)
            
            # General Jitter Multiplier (WAN delay)
            jitter = np.random.uniform(0.01, 0.05) 
            
            if cls == "voip":
                pkt_count = int(np.random.normal(500, 100))
                mean_len = np.random.normal(210, 10) 
                std_len = np.random.uniform(5, 15)  # Higher variance due to fragmentation/retransmits
                mean_iat = np.random.normal(0.02, 0.005)
                std_iat = np.random.uniform(0.005, 0.015) # Jitter destroys perfect 20ms pacing
                max_len = mean_len + 50
                min_len = mean_len - 50
                
            elif cls == "video":
                pkt_count = int(np.random.normal(3000, 800))
                mean_len = np.random.normal(1200, 150)
                std_len = np.random.uniform(400, 600) 
                mean_iat = np.random.normal(0.005, 0.002)
                std_iat = np.random.uniform(0.02, 0.08) 
                max_len = 1360
                min_len = 64
                
            elif cls == "web":
                pkt_count = int(np.random.normal(200, 80))
                direction_ratio = np.random.uniform(0.1, 0.4) 
                mean_len = np.random.normal(800, 250)
                std_len = np.random.uniform(400, 650)
                mean_iat = np.random.normal(0.1, 0.08)
                std_iat = np.random.uniform(0.1, 0.6)
                max_len = 1360
                min_len = 64
                
            elif cls == "icmp":
                pkt_count = int(np.random.normal(30, 5))
                mean_len = np.random.normal(120, 5)
                std_len = np.random.uniform(0, 2)
                mean_iat = np.random.normal(1.0, 0.05)
                std_iat = np.random.uniform(0.01, 0.05)
                max_len = mean_len + 5
                min_len = mean_len - 5
                
            elif cls == "bulk":
                pkt_count = int(np.random.normal(5000, 1500))
                mean_len = np.random.normal(1300, 80)
                std_len = np.random.uniform(20, 80)
                mean_iat = np.random.normal(0.001, 0.0008)
                std_iat = np.random.uniform(0.001, 0.005)
                max_len = 1360
                min_len = 64
                
            elif cls == "email":
                pkt_count = int(np.random.normal(50, 15))
                mean_len = np.random.normal(400, 120)
                std_len = np.random.uniform(200, 350)
                mean_iat = np.random.normal(0.5, 0.3)
                std_iat = np.random.uniform(0.1, 0.6)
                max_len = 1000
                min_len = 64
                
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
    df.to_csv("data/iscx_features.csv", index=False)
    print(f"Generated {len(df)} ISCX validation flows with WAN jitter.")

if __name__ == "__main__":
    generate_iscx_features()
