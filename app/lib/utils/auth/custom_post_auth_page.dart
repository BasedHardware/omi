const String customPostAuthHtml = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Complete</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'SF Pro Display', Roboto, 'Helvetica Neue', Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #0F0F0F;
            color: #FFFFFF;
            overflow: hidden;
            position: relative;
        }
        
        /* Subtle background pattern */
        body::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 25% 25%, #1A1A1A 0%, transparent 50%),
                radial-gradient(circle at 75% 75%, #252525 0%, transparent 50%);
            opacity: 0.5;
        }
        
        .container {
            text-align: center;
            max-width: 420px;
            padding: 3rem 2rem;
            position: relative;
            z-index: 10;
            animation: slideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .success-icon {
            width: 72px;
            height: 72px;
            background: #252525;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 2rem;
            border: 1px solid #2A2A2A;
            position: relative;
            animation: scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.2s both;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }
        
        .success-icon::before {
            content: '';
            position: absolute;
            inset: -1px;
            background: linear-gradient(135deg, #10B981, #059669);
            border-radius: 50%;
            z-index: -1;
            opacity: 0;
            animation: glowPulse 2s ease-in-out infinite 1s;
        }
        
        .success-icon svg {
            width: 32px;
            height: 32px;
            fill: #10B981;
            filter: drop-shadow(0 2px 8px rgba(16, 185, 129, 0.3));
        }
        
        h1 {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.75rem;
            letter-spacing: -0.02em;
            color: #FFFFFF;
            animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both;
        }
        
        .subtitle {
            font-size: 1rem;
            color: #E5E5E5;
            margin-bottom: 2.5rem;
            font-weight: 400;
            line-height: 1.5;
            animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.4s both;
        }
        
        .status-card {
            background: #1A1A1A;
            border: 1px solid #252525;
            border-radius: 16px;
            padding: 1.5rem;
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.5s both;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
        }
        
        .status-header {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            background: #10B981;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }
        
        .status-text {
            font-size: 0.875rem;
            color: #B0B0B0;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .countdown-display {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        
        .countdown-number {
            font-size: 1.5rem;
            font-weight: 800;
            color: #FFFFFF;
            font-variant-numeric: tabular-nums;
            min-width: 28px;
        }
        
        .countdown-label {
            font-size: 0.875rem;
            color: #888888;
            font-weight: 500;
        }
        
        .progress-container {
            position: relative;
            height: 3px;
            background: #252525;
            border-radius: 2px;
            overflow: hidden;
        }
        
        .progress-bar {
            position: absolute;
            top: 0;
            left: 0;
            height: 100%;
            background: linear-gradient(90deg, #10B981 0%, #059669 100%);
            border-radius: 2px;
            transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(40px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes scaleIn {
            from {
                opacity: 0;
                transform: scale(0.8);
            }
            to {
                opacity: 1;
                transform: scale(1);
            }
        }
        
        @keyframes pulse {
            0%, 100% {
                opacity: 1;
                transform: scale(1);
            }
            50% {
                opacity: 0.7;
                transform: scale(1.1);
            }
        }
        
        @keyframes glowPulse {
            0%, 100% {
                opacity: 0;
            }
            50% {
                opacity: 0.3;
            }
        }
        
        /* Responsive Design */
        @media (max-width: 480px) {
            .container {
                padding: 2rem 1.5rem;
                max-width: 90vw;
            }
            
            h1 {
                font-size: 1.75rem;
            }
            
            .success-icon {
                width: 64px;
                height: 64px;
            }
            
            .success-icon svg {
                width: 28px;
                height: 28px;
            }
            
            .status-card {
                padding: 1.25rem;
            }
        }
        
        @media (max-height: 600px) {
            .container {
                padding: 2rem;
            }
            
            .success-icon {
                margin-bottom: 1.5rem;
            }
            
            .subtitle {
                margin-bottom: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">
            <svg viewBox="0 0 24 24">
                <path d="M9,20.42L2.79,14.21L5.21,11.79L9,15.58L18.79,5.79L21.21,8.21L9,20.42Z"/>
            </svg>
        </div>
        
        <h1>Authentication Complete</h1>
        <div class="subtitle">Successfully signed in to your account</div>
        
        <div class="status-card">
            <div class="status-header">
                <div class="status-dot"></div>
                <div class="status-text">Window Closing</div>
            </div>
            
            <div class="countdown-display">
                <span class="countdown-number" id="countdown">3</span>
                <span class="countdown-label">seconds</span>
            </div>
            
            <div class="progress-container">
                <div class="progress-bar" id="progressBar" style="width: 100%;"></div>
            </div>
        </div>
    </div>
    
    <script>
        let countdown = 3;
        const countdownElement = document.getElementById('countdown');
        const progressBar = document.getElementById('progressBar');
        
        const timer = setInterval(() => {
            countdown--;
            countdownElement.textContent = countdown;
            
            // Update progress bar
            const progress = (countdown / 3) * 100;
            progressBar.style.width = progress + '%';
            
            if (countdown <= 0) {
                clearInterval(timer);
                countdownElement.textContent = '0';
                progressBar.style.width = '0%';
                try {
                    window.close();
                } catch (e) {
                    console.log('Cannot auto-close window');
                }
            }
        }, 1000);
    </script>
</body>
</html>
''';
