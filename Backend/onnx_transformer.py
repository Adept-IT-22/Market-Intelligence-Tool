import os
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

class ONNXTransformer:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        
        # Load ONNX session with default CPU execution provider
        model_path = os.path.join(model_dir, "model.onnx")
        
        # Optimize execution providers (prefer CPU since this runs locally)
        self.session = ort.InferenceSession(
            model_path, 
            providers=["CPUExecutionProvider"]
        )

    def encode(
        self, 
        sentences, 
        batch_size: int = 32, 
        show_progress_bar: bool = False, 
        convert_to_numpy: bool = True,
        **kwargs
    ):
        """
        Drop-in replacement for SentenceTransformer.encode.
        Accepts a single string or a list of strings.
        """
        is_single_string = isinstance(sentences, str)
        if is_single_string:
            sentences = [sentences]

        embeddings = []
        
        # Process in batches
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i : i + batch_size]
            
            # Tokenize batch
            inputs = self.tokenizer(
                batch, 
                padding=True, 
                truncation=True, 
                max_length=512, 
                return_tensors="np"
            )
            
            # Convert inputs to int64 (ONNX expectation)
            onnx_inputs = {k: v.astype(np.int64) for k, v in inputs.items()}
            
            # Run inference
            outputs = self.session.run(None, onnx_inputs)
            
            # BGE model uses CLS pooling
            last_hidden_state = outputs[0]
            cls_tokens = last_hidden_state[:, 0, :]
            
            # L2 Normalize
            norms = np.linalg.norm(cls_tokens, axis=1, keepdims=True)
            # Prevent division by zero
            norms = np.clip(norms, a_min=1e-9, a_max=None)
            normalized_cls = cls_tokens / norms
            
            embeddings.append(normalized_cls)
            
        # Concatenate batches
        all_embeddings = np.vstack(embeddings)
        
        if is_single_string:
            return all_embeddings[0] if convert_to_numpy else all_embeddings[0].tolist()
            
        return all_embeddings if convert_to_numpy else all_embeddings.tolist()
