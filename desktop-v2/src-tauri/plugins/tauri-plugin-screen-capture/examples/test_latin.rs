use kreuzberg_paddle_ocr::OcrLite;
use std::path::Path;

fn main() {
    let models_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("models");
    
    let det_path = models_dir.join("ch_PP-OCRv4_det_infer.onnx");
    let cls_path = models_dir.join("ch_ppocr_mobile_v2.0_cls_train.onnx");
    let rec_path = models_dir.join("latin_rec.onnx");
    let dict_path = models_dir.join("latin_dict.txt");
    
    println!("Loading models...");
    let mut ocr = OcrLite::new();
    ocr.init_models_with_dict(
        det_path.to_str().unwrap(),
        cls_path.to_str().unwrap(),
        rec_path.to_str().unwrap(),
        dict_path.to_str().unwrap(),
        2,
    ).expect("Failed to init models");
    println!("Models loaded!");
    
    let img = image::open("/tmp/test_screenshot.png").expect("Failed to open image").to_rgb8();
    println!("Image: {}x{}", img.width(), img.height());
    
    let result = ocr.detect(&img, 10, 1920, 0.5, 0.3, 1.6, false, false)
        .expect("OCR failed");
    
    println!("\n=== Latin OCR ({} blocks) ===", result.text_blocks.len());
    for (i, block) in result.text_blocks.iter().take(15).enumerate() {
        println!("[{}] score={:.3} text=\"{}\"", i, block.text_score, block.text);
    }
}
