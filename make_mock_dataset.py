import pandas as pd
import numpy as np

# Create a synthetic dataset for testing the anti-draw model
np.random.seed(42)

# Generate synthetic data
n_samples = 500

data = {
    'home_form': np.random.uniform(0.5, 2.5, n_samples),
    'away_form': np.random.uniform(0.5, 2.5, n_samples),
    'home_goals_avg': np.random.uniform(0.5, 2.5, n_samples),
    'away_goals_avg': np.random.uniform(0.5, 2.5, n_samples),
    'home_conceded_avg': np.random.uniform(0.3, 2.0, n_samples),
    'away_conceded_avg': np.random.uniform(0.3, 2.0, n_samples),
    'home_goal_diff_avg': np.random.uniform(-1.5, 1.5, n_samples),
    'away_goal_diff_avg': np.random.uniform(-1.5, 1.5, n_samples),
    'home_win_rate': np.random.uniform(0.2, 0.7, n_samples),
    'away_win_rate': np.random.uniform(0.2, 0.7, n_samples),
    'home_clean_sheet_rate': np.random.uniform(0.1, 0.5, n_samples),
    'away_clean_sheet_rate': np.random.uniform(0.1, 0.5, n_samples),
    'home_failed_to_score_rate': np.random.uniform(0.1, 0.4, n_samples),
    'away_failed_to_score_rate': np.random.uniform(0.1, 0.4, n_samples),
    'is_international': np.random.choice([0, 1], n_samples),
}

df = pd.DataFrame(data)

# Generate results based on team strength with realistic distribution
# 45% home wins, 30% draws, 25% away wins (realistic football)
results = []
for i in range(n_samples):
    home_strength = (df.loc[i, 'home_form'] + df.loc[i, 'home_goals_avg'] + df.loc[i, 'home_win_rate']) / 3
    away_strength = (df.loc[i, 'away_form'] + df.loc[i, 'away_goals_avg'] + df.loc[i, 'away_win_rate']) / 3
    
    diff = home_strength - away_strength
    
    if diff > 0.3:
        results.append(2)  # Home win
    elif diff < -0.3:
        results.append(0)  # Away win
    else:
        results.append(1)  # Draw

df['result'] = results

# Save to CSV
df.to_csv('dataset.csv', index=False)

print(f"✅ Mock dataset created: dataset.csv")
print(f"   Total samples: {len(df)}")
print(f"   Columns: {list(df.columns)}")
print(f"\nResult distribution:")
print(df['result'].value_counts().sort_index())
print(f"\nHome Win: {(df['result']==2).sum()/len(df)*100:.1f}%")
print(f"Draw: {(df['result']==1).sum()/len(df)*100:.1f}%")
print(f"Away Win: {(df['result']==0).sum()/len(df)*100:.1f}%")
