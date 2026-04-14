use kreuzberg_paddle_ocr::OcrLite;
use std::path::Path;

fn main() {
    let models_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("models");
    
    let det_path = models_dir.join("ch_PP-OCRv4_det_infer.onnx");
    let cls_path = models_dir.join("ch_ppocr_mobile_v2.0_cls_train.onnx");
    let rec_path = models_dir.join("en_PP-OCRv3_rec_infer.onnx");
    let dict_path = models_dir.join("en_dict.txt");
    
    println!("Loading models...");
    println!("  det: {} (exists: {})", det_path.display(), det_path.exists());
    println!("  cls: {} (exists: {})", cls_path.display(), cls_path.exists());
    println!("  rec: {} (exists: {})", rec_path.display(), rec_path.exists());
    println!("  dict: {} (exists: {})", dict_path.display(), dict_path.exists());
    
    // Check dict contents
    let dict = std::fs::read_to_string(&dict_path).unwrap();
    println!("  dict lines: {}, first 10: {:?}", dict.lines().count(), dict.lines().take(10).collect::<Vec<_>>());
    
    let mut ocr = OcrLite::new();
    ocr.init_models_with_dict(
        det_path.to_str().unwrap(),
        cls_path.to_str().unwrap(),
        rec_path.to_str().unwrap(),
        dict_path.to_str().unwrap(),
        2,
    ).expect("Failed to init models");
    
    println!("Models loaded!");
    
    // Load test image
    let img = image::open("/tmp/test_screenshot.png").expect("Failed to open image").to_rgb8();
    println!("Image: {}x{}", img.width(), img.height());
    
    // Run OCR
    println!("Running OCR...");
    let result = ocr.detect(
        &img,
        10,    // padding
        1920,  // max_side_len
        0.5,   // box_score_thresh
        0.3,   // box_thresh
        1.6,   // un_clip_ratio
        false, // do_angle
        false, // most_angle
    ).expect("OCR failed");
    
    println!("\n=== OCR Results ({} blocks) ===", result.text_blocks.len());
    for (i, block) in result.text_blocks.iter().enumerate() {
        println!("[{}] score={:.3} text=\"{}\"", i, block.text_score, block.text);
    }
}
