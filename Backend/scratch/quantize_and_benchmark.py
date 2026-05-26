import os
import time
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
import onnxruntime as ort

def benchmark_models():
    model_id = "BAAI/bge-small-en"
    onnx_model_path = "./model_onnx"
    quantized_model_path = "./model_onnx_quantized"
    
    text = "What is the projected ROI for new solar energy investments?"
    
    # 1. PyTorch / SentenceTransformer Benchmark
    print("Benchmarking PyTorch (SentenceTransformer)...")
    st_model = SentenceTransformer(model_id)
    # Warmup
    _ = st_model.encode(text)
    
    start = time.perf_counter()
    for _ in range(50):
        st_emb = st_model.encode(text, convert_to_numpy=True)
    st_time = (time.perf_counter() - start) / 50 * 1000
    st_emb = st_emb / np.linalg.norm(st_emb)
    print(f"ST latency: {st_time:.2f} ms")
    
    # 2. Quantize the model if not already quantized
    if not os.path.exists(quantized_model_path) or not os.path.exists(os.path.join(quantized_model_path, "model_quantized.onnx")):
        print("Quantizing ONNX model...")
        from optimum.onnxruntime import ORTQuantizer
        from optimum.onnxruntime.configuration import AutoQuantizationConfig
        
        quantizer = ORTQuantizer.from_pretrained(onnx_model_path, file_name="model.onnx")
        qconfig = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
        quantizer.quantize(save_dir=quantized_model_path, quantization_config=qconfig)
        
        # Copy tokenizer config files
        import shutil
        for f in os.listdir(onnx_model_path):
            if f != "model.onnx" and not os.path.exists(os.path.join(quantized_model_path, f)):
                shutil.copy(os.path.join(onnx_model_path, f), os.path.join(quantized_model_path, f))
    
    # 3. Raw ONNX Benchmark
    print("Benchmarking Raw ONNX...")
    tokenizer = AutoTokenizer.from_pretrained(onnx_model_path)
    session_raw = ort.InferenceSession(os.path.join(onnx_model_path, "model.onnx"))
    
    inputs = tokenizer(text, padding=True, truncation=True, return_tensors="np")
    onnx_inputs = {k: v.astype(np.int64) for k, v in inputs.items()}
    
    # Warmup
    _ = session_raw.run(None, onnx_inputs)
    
    start = time.perf_counter()
    for _ in range(50):
        outputs = session_raw.run(None, onnx_inputs)
        last_hidden_state = outputs[0]
        cls_token = last_hidden_state[0, 0, :]
        raw_emb = cls_token / np.linalg.norm(cls_token)
    raw_time = (time.perf_counter() - start) / 50 * 1000
    print(f"Raw ONNX latency: {raw_time:.2f} ms")
    print(f"Raw ONNX Similarity to PyTorch: {np.dot(st_emb, raw_emb):.5f}")
    
    # 4. Quantized ONNX Benchmark
    print("Benchmarking Quantized ONNX...")
    session_quant = ort.InferenceSession(os.path.join(quantized_model_path, "model_quantized.onnx"))
    
    # Warmup
    _ = session_quant.run(None, onnx_inputs)
    
    start = time.perf_counter()
    for _ in range(50):
        outputs = session_quant.run(None, onnx_inputs)
        last_hidden_state = outputs[0]
        cls_token = last_hidden_state[0, 0, :]
        quant_emb = cls_token / np.linalg.norm(cls_token)
    quant_time = (time.perf_counter() - start) / 50 * 1000
    print(f"Quantized ONNX latency: {quant_time:.2f} ms")
    print(f"Quantized ONNX Similarity to PyTorch: {np.dot(st_emb, quant_emb):.5f}")

if __name__ == "__main__":
    benchmark_models()
