import pandas as pd

df = pd.read_csv('data/sold_1yr.csv')

# Remove rows with missing values in Sq Ft Total and Lot Size
df = df.dropna(subset=['Sq Ft Total', 'Lot Size'])

# Clean Lot Size: remove commas and "Lot SqFt" text, convert to integer
df['Lot Size'] = df['Lot Size'].str.replace(',', '').str.replace(' Lot SqFt', '', regex=False).astype(int)

# Filter rows where Lot Size >= 5000
df = df[df['Lot Size'] >= 5000]

df['Sq Ft Total'] = df['Sq Ft Total'].str.replace(',', '').astype(int)

# Clean Price: remove commas, convert to integer
df['Price'] = df['Price'].str.replace('$', '', regex=False).str.replace(',', '').astype(int)

# Calculate PPSF with conditional weighting based on lot-to-building ratio
# If lot size is 5+ times the sq ft, prioritize lot size (90% weight)
# Otherwise use standard weights (70% lot, 30% sq ft)
def calculate_ppsf(row):
    if row['Lot Size'] >= 5 * row['Sq Ft Total']:
        return row['Price'] / (0.9 * row['Sq Ft Total'] + 0.1 * row['Lot Size'])
    else:
        return row['Price'] / (1 * row['Sq Ft Total'] + 0 * row['Lot Size'])

df['PPSF'] = df.apply(calculate_ppsf, axis=1)

# Sort by PPSF in ascending order (lowest first, highest last)
df = df.sort_values(by='PPSF')

pd.set_option('display.max_columns', None)

# Calculate optimal PPSF as the 10th percentile (dynamic market-based benchmark)
optimal_PPSF = df['PPSF'].quantile(0.1)
print (f"Median PPSF: ${df['PPSF'].quantile(0.5):.2f}")
print(f"Optimal PPSF (10th percentile): ${optimal_PPSF:.2f}")
print(f"Properties with PPSF at or below optimal: {len(df[df['PPSF'] <= optimal_PPSF])}")
print(df['PPSF'])
#print(df)