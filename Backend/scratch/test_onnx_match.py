import os
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
import onnxruntime as ort

def test_match():
    # 1. Original SentenceTransformer encoding
    model_id = "BAAI/bge-small-en"
    st_model = SentenceTransformer(model_id)
    text = "What is the projected ROI for solar energy?"
    st_emb = st_model.encode(text, convert_to_numpy=True)
    
    # Normalize original ST embedding (just in case)
    st_emb = st_emb / np.linalg.norm(st_emb)
    print("ST Embedding norm:", np.linalg.norm(st_emb))
    print("ST Embedding shape:", st_emb.shape)
    
    # 2. Export using Optimum
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    onnx_model_path = "./model_onnx"
    if not os.path.exists(onnx_model_path) or not os.path.exists(os.path.join(onnx_model_path, "vocab.txt")):
        print("Exporting model and tokenizer to ONNX...")
        model = ORTModelForFeatureExtraction.from_pretrained(model_id, export=True)
        model.save_pretrained(onnx_model_path)
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        tokenizer.save_pretrained(onnx_model_path)
    
    # Load tokenizer and ONNX session
    tokenizer = AutoTokenizer.from_pretrained(onnx_model_path)
    session = ort.InferenceSession(os.path.join(onnx_model_path, "model.onnx"))
    
    # Tokenize input
    inputs = tokenizer(text, padding=True, truncation=True, return_tensors="np")
    # Convert inputs to int64 for ONNX Runtime (standard for HF models)
    onnx_inputs = {k: v.astype(np.int64) for k, v in inputs.items()}
    
    # Run ONNX inference
    outputs = session.run(None, onnx_inputs)
    # The output shapes: [0] is usually last_hidden_state [batch_size, seq_len, hidden_dim]
    last_hidden_state = outputs[0]
    print("ONNX last_hidden_state shape:", last_hidden_state.shape)
    
    # BGE models use CLS pooling: the embedding is the [CLS] token (first token) normalized.
    # Let's extract the CLS token
    cls_token = last_hidden_state[0, 0, :]
    # Normalize CLS token
    onnx_emb = cls_token / np.linalg.norm(cls_token)
    
    # Check cosine similarity / match
    similarity = np.dot(st_emb, onnx_emb)
    print("CLS Token matching similarity:", similarity)
    
    # Let's check if it uses Mean pooling instead
    # Mean pooling: sum over seq_len with attention mask, then divide by sum of attention mask
    input_mask_expanded = np.expand_dims(inputs['attention_mask'], -1).astype(float)
    sum_embeddings = np.sum(last_hidden_state * input_mask_expanded, axis=1)
    sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
    mean_emb = sum_embeddings / sum_mask
    mean_emb = mean_emb[0]
    mean_emb = mean_emb / np.linalg.norm(mean_emb)
    
    mean_similarity = np.dot(st_emb, mean_emb)
    print("Mean pooling matching similarity:", mean_similarity)

if __name__ == "__main__":
    test_match()
