import pandas as pd
import zipfile
import json
import pypdf 

zip_path = "data/trockenheitsdaten-numerisch_reference__trockenheitsdaten-numerisch_reference.csv.zip"
internal_csv_path = "regions.csv"

# 1. Read Regions directly from the ZIP
with zipfile.ZipFile(zip_path, 'r') as z:
    with z.open(internal_csv_path) as f:
        df_regions = pd.read_csv(f, sep=';', skiprows=3)

regions = df_regions['name_de'].str.strip().tolist()
region_to_id = {row['name_de'].strip(): row['drought_region_id'] for _, row in df_regions.iterrows()}

# 2. Extract text from the PDF
with open('data/stations.pdf', 'rb') as f:
    reader = pypdf.PdfReader(f)
    text = "".join(page.extract_text() + "\n" for page in reader.pages)

# Locate the table start
start_idx = text.find("Stations nummer")
if start_idx == -1:
    start_idx = text.find("Stationsnummer")

table_text = text[start_idx:]
lines = table_text.split('\n')

station_mapping = {}

# 3. Parse lines and match regions
for line in lines[1:]:
    line = line.strip()
    if not line:
        continue
    
    matched_region = None
    for r in sorted(regions, key=len, reverse=True):
        if line.endswith(r):
            matched_region = r
            break
            
    if matched_region:
        tokens = line.split()
        if tokens:
            station_num = tokens[0]
            if station_num.startswith('*'):
                station_num = station_num[1:]
                
            region_id = region_to_id[matched_region]
            station_mapping[station_num] = int(region_id)

# 4. Write output
with open("data/station_region_mapping.json", "w") as f:
    json.dump(station_mapping, f, indent=4)