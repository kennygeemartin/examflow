"""Run this cell in the ORIGINAL Colab notebook after the training/tokenizer cell.
Change `tokenizer` below only if your notebook used a different variable name.
Do not fit a replacement tokenizer on a new corpus.
"""
from google.colab import files

with open('tokenizer.json', 'w', encoding='utf-8') as output:
    output.write(tokenizer.to_json())
files.download('tokenizer.json')

# Place the downloaded file in this project's models/tokenizer.json.
# Also download the original .ipynb notebook for checking preprocessing,
# padding/truncation and any generation settings against the adapter.
