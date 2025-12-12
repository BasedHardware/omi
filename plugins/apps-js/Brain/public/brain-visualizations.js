/**
 * Brain App - Advanced Visualization Features
 * Includes: Heat Map, Timeline, Cluster View, and Performance Optimizations
 */

// ===== Data Visualization Manager =====
class BrainVisualizationManager {
    constructor() {
        this.currentView = 'graph'; // graph | heatmap | timeline | cluster
        this.memoryData = null;
        this.virtualScroller = null;
        this.imageLoader = null;
        this.worker = null;
        this.initializeComponents();
    }

    initializeComponents() {
        // Initialize lazy image loader
        this.imageLoader = new LazyImageLoader();
        
        // Initialize virtual scroller for long lists
        this.virtualScroller = new VirtualScroller();
        
        // Initialize Web Worker for heavy processing
        if (window.Worker) {
            this.initializeWebWorker();
        }
    }

    initializeWebWorker() {
        // Create inline worker for memory processing
        const workerCode = `
            self.addEventListener('message', function(e) {
                const { type, data } = e.data;
                
                switch(type) {
                    case 'processMemories':
                        const processed = processMemoryData(data);
                        self.postMessage({ type: 'memoriesProcessed', data: processed });
                        break;
                    
                    case 'calculateClusters':
                        const clusters = calculateClusters(data);
                        self.postMessage({ type: 'clustersCalculated', data: clusters });
                        break;
                    
                    case 'generateHeatmap':
                        const heatmap = generateHeatmapData(data);
                        self.postMessage({ type: 'heatmapGenerated', data: heatmap });
                        break;
                }
            });
            
            function processMemoryData(memories) {
                // Heavy processing of memory data
                return memories.map(memory => ({
                    ...memory,
                    processed: true,
                    timestamp: new Date(memory.created_at).getTime()
                }));
            }
            
            function calculateClusters(nodes) {
                // K-means clustering algorithm
                const k = Math.min(5, Math.floor(nodes.length / 10));
                const clusters = [];
                // Simplified clustering logic
                for (let i = 0; i < k; i++) {
                    clusters.push({
                        id: i,
                        nodes: nodes.filter((_, idx) => idx % k === i),
                        center: { x: Math.random() * 200 - 100, y: Math.random() * 200 - 100 }
                    });
                }
                return clusters;
            }
            
            function generateHeatmapData(memories) {
                // Generate density map
                const grid = {};
                memories.forEach(memory => {
                    const key = Math.floor(memory.x / 50) + ',' + Math.floor(memory.y / 50);
                    grid[key] = (grid[key] || 0) + 1;
                });
                return grid;
            }
        `;
        
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        this.worker = new Worker(URL.createObjectURL(blob));
        
        this.worker.addEventListener('message', (e) => {
            this.handleWorkerMessage(e.data);
        });
    }

    handleWorkerMessage(message) {
        const { type, data } = message;
        
        switch(type) {
            case 'memoriesProcessed':
                this.updateVisualization(data);
                break;
            case 'clustersCalculated':
                this.renderClusterView(data);
                break;
            case 'heatmapGenerated':
                this.renderHeatmap(data);
                break;
        }
    }

    // ===== View Switching =====
    switchView(viewType) {
        this.currentView = viewType;
        
        // Add view controls to UI
        this.addViewControls();
        
        switch(viewType) {
            case 'heatmap':
                this.showHeatmapView();
                break;
            case 'timeline':
                this.showTimelineView();
                break;
            case 'cluster':
                this.showClusterView();
                break;
            default:
                this.showGraphView();
        }
    }

    addViewControls() {
        // Check if controls already exist
        if (document.getElementById('view-controls')) return;
        
        const controlsHTML = `
            <div id="view-controls" class="view-controls">
                <button class="view-btn ${this.currentView === 'graph' ? 'active' : ''}" 
                        onclick="brainViz.switchView('graph')"
                        title="Graph View (Ctrl/Cmd + 1)">
                    <span class="icon">🕸️</span> <span class="btn-text">Graph</span>
                </button>
                <button class="view-btn ${this.currentView === 'heatmap' ? 'active' : ''}" 
                        onclick="brainViz.switchView('heatmap')"
                        title="Heat Map View (Ctrl/Cmd + 2)">
                    <span class="icon">🗺️</span> <span class="btn-text">Heat Map</span>
                </button>
                <button class="view-btn ${this.currentView === 'timeline' ? 'active' : ''}" 
                        onclick="brainViz.switchView('timeline')"
                        title="Timeline View (Ctrl/Cmd + 3)">
                    <span class="icon">📅</span> <span class="btn-text">Timeline</span>
                </button>
                <button class="view-btn ${this.currentView === 'cluster' ? 'active' : ''}" 
                        onclick="brainViz.switchView('cluster')"
                        title="Cluster View (Ctrl/Cmd + 4)">
                    <span class="icon">🫧</span> <span class="btn-text">Clusters</span>
                </button>
            </div>
            
            <!-- Mobile Control Buttons -->
            <div id="mobile-view-controls" class="mobile-view-controls">
                <button class="mobile-control-btn back-to-graph ${this.currentView === 'graph' ? 'hidden' : ''}" 
                        onclick="brainViz.switchView('graph')"
                        title="Back to Graph">
                    <span>←</span> Back
                </button>
                <button class="mobile-control-btn help-btn" 
                        onclick="brainViz.showKeyboardHelp()"
                        title="Help">
                    <span>?</span>
                </button>
            </div>
        `;
        
        const container = document.getElementById('network-container');
        container.insertAdjacentHTML('afterbegin', controlsHTML);
        
        // Add styles
        this.addViewControlStyles();
    }

    addViewControlStyles() {
        if (document.getElementById('viz-styles')) return;
        
        const styles = `
            <style id="viz-styles">
                .view-controls {
                    position: absolute;
                    top: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    display: flex;
                    gap: 10px;
                    background: rgba(15, 15, 25, 0.9);
                    padding: 10px;
                    border-radius: 12px;
                    border: 1px solid rgba(0, 255, 170, 0.2);
                    backdrop-filter: blur(10px);
                    z-index: 100;
                }
                
                .view-btn {
                    background: rgba(0, 255, 170, 0.1);
                    border: 1px solid rgba(0, 255, 170, 0.3);
                    color: #00ffaa;
                    padding: 8px 16px;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    font-size: 14px;
                }
                
                .view-btn:hover {
                    background: rgba(0, 255, 170, 0.2);
                    transform: translateY(-2px);
                }
                
                .view-btn.active {
                    background: rgba(0, 255, 170, 0.3);
                    border-color: #00ffaa;
                }
                
                .heatmap-canvas {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                }
                
                .timeline-container {
                    position: absolute;
                    bottom: 20px;
                    left: 20px;
                    right: 20px;
                    height: 200px;
                    background: rgba(15, 15, 25, 0.9);
                    border: 1px solid rgba(0, 255, 170, 0.2);
                    border-radius: 12px;
                    padding: 20px;
                    overflow-x: auto;
                }
                
                .cluster-info {
                    position: absolute;
                    top: 80px;
                    right: 20px;
                    width: 250px;
                    background: rgba(15, 15, 25, 0.9);
                    border: 1px solid rgba(0, 255, 170, 0.2);
                    border-radius: 12px;
                    padding: 15px;
                }
                
                .memory-tooltip {
                    position: absolute;
                    background: rgba(15, 15, 25, 0.95);
                    border: 1px solid rgba(0, 255, 170, 0.3);
                    border-radius: 8px;
                    padding: 10px;
                    color: #fff;
                    font-size: 12px;
                    pointer-events: none;
                    z-index: 1000;
                    max-width: 200px;
                }
                
                /* Mobile Control Buttons */
                .mobile-view-controls {
                    display: none;
                    position: fixed;
                    bottom: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    z-index: 101;
                    gap: 10px;
                }
                
                .mobile-control-btn {
                    background: rgba(15, 15, 25, 0.95);
                    border: 2px solid rgba(0, 255, 170, 0.3);
                    color: #00ffaa;
                    padding: 12px 20px;
                    border-radius: 25px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 16px;
                    font-weight: 500;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
                }
                
                .mobile-control-btn:hover {
                    background: rgba(0, 255, 170, 0.2);
                    transform: translateY(-2px);
                    box-shadow: 0 6px 30px rgba(0, 255, 170, 0.3);
                }
                
                .mobile-control-btn.back-to-graph {
                    background: rgba(0, 255, 170, 0.15);
                }
                
                .mobile-control-btn.help-btn {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    left: auto;
                    transform: none;
                    width: 50px;
                    height: 50px;
                    border-radius: 50%;
                    padding: 0;
                    justify-content: center;
                    font-size: 20px;
                    background: rgba(255, 165, 0, 0.15);
                    border-color: rgba(255, 165, 0, 0.5);
                    color: #ffa500;
                }
                
                .mobile-control-btn.help-btn:hover {
                    background: rgba(255, 165, 0, 0.25);
                    box-shadow: 0 6px 30px rgba(255, 165, 0, 0.3);
                }
                
                .mobile-control-btn.hidden {
                    display: none !important;
                }
                
                /* Show mobile controls on touch devices */
                @media (pointer: coarse), (max-width: 768px) {
                    .mobile-view-controls {
                        display: flex;
                    }
                    
                    /* Make view control buttons more compact on mobile */
                    .view-controls {
                        flex-wrap: wrap;
                        max-width: calc(100% - 80px);
                    }
                    
                    .view-btn .btn-text {
                        display: none;
                    }
                    
                    .view-btn {
                        padding: 10px;
                        min-width: 45px;
                    }
                }
                
                /* Landscape mobile adjustments */
                @media (max-height: 500px) and (orientation: landscape) {
                    .view-controls {
                        top: 10px;
                        padding: 5px;
                    }
                    
                    .mobile-view-controls {
                        bottom: 10px;
                    }
                    
                    .mobile-control-btn {
                        padding: 8px 16px;
                        font-size: 14px;
                    }
                    
                    .mobile-control-btn.help-btn {
                        width: 40px;
                        height: 40px;
                        font-size: 18px;
                    }
                }
            </style>
        `;
        
        document.head.insertAdjacentHTML('beforeend', styles);
    }

    // ===== Heat Map View =====
    showHeatmapView() {
        if (!this.memoryData) {
            this.loadMemoryData().then(() => this.createHeatmap());
        } else {
            this.createHeatmap();
        }
    }

    createHeatmap() {
        // Clear existing Three.js scene if present
        const container = document.getElementById('network-container');
        
        // Create canvas for heatmap
        const canvas = document.createElement('canvas');
        canvas.className = 'heatmap-canvas';
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
        container.appendChild(canvas);
        
        const ctx = canvas.getContext('2d');
        
        // Process data in Web Worker if available
        if (this.worker) {
            this.worker.postMessage({ 
                type: 'generateHeatmap', 
                data: this.memoryData 
            });
        } else {
            this.renderHeatmapDirect(ctx);
        }
    }

    renderHeatmap(gridData) {
        const canvas = document.querySelector('.heatmap-canvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const cellSize = 50;
        
        // Find max density for normalization
        const maxDensity = Math.max(...Object.values(gridData));
        
        // Draw heatmap
        Object.entries(gridData).forEach(([key, density]) => {
            const [x, y] = key.split(',').map(Number);
            const intensity = density / maxDensity;
            
            // Create gradient from blue to red based on density
            const hue = (1 - intensity) * 240; // Blue to red
            ctx.fillStyle = `hsla(${hue}, 100%, 50%, ${0.3 + intensity * 0.7})`;
            
            ctx.fillRect(
                x * cellSize + canvas.width / 2,
                y * cellSize + canvas.height / 2,
                cellSize,
                cellSize
            );
        });
        
        // Add legend
        this.drawHeatmapLegend(ctx);
    }

    drawHeatmapLegend(ctx) {
        const legendWidth = 200;
        const legendHeight = 20;
        const x = 20;
        const y = 20;
        
        // Create gradient
        const gradient = ctx.createLinearGradient(x, y, x + legendWidth, y);
        gradient.addColorStop(0, 'hsl(240, 100%, 50%)'); // Blue (low)
        gradient.addColorStop(1, 'hsl(0, 100%, 50%)');   // Red (high)
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x, y, legendWidth, legendHeight);
        
        // Add labels
        ctx.fillStyle = '#fff';
        ctx.font = '12px Inter';
        ctx.fillText('Low Density', x, y - 5);
        ctx.fillText('High Density', x + legendWidth - 70, y - 5);
    }

    // ===== Timeline View =====
    showTimelineView() {
        if (!this.memoryData) {
            this.loadMemoryData().then(() => this.createTimeline());
        } else {
            this.createTimeline();
        }
    }

    createTimeline() {
        const container = document.getElementById('network-container');
        
        // Create timeline container
        const timelineDiv = document.createElement('div');
        timelineDiv.className = 'timeline-container';
        timelineDiv.id = 'timeline-view';
        container.appendChild(timelineDiv);
        
        // Sort memories by date
        const sortedMemories = [...(this.memoryData || [])].sort((a, b) => 
            new Date(a.created_at) - new Date(b.created_at)
        );
        
        // Group by day
        const groupedByDay = this.groupMemoriesByDay(sortedMemories);
        
        // Create timeline visualization
        this.renderTimeline(groupedByDay, timelineDiv);
    }

    groupMemoriesByDay(memories) {
        const groups = {};
        
        memories.forEach(memory => {
            const date = new Date(memory.created_at).toLocaleDateString();
            if (!groups[date]) {
                groups[date] = [];
            }
            groups[date].push(memory);
        });
        
        return groups;
    }

    renderTimeline(groupedMemories, container) {
        const timelineHTML = Object.entries(groupedMemories).map(([date, memories]) => `
            <div class="timeline-day">
                <div class="timeline-date">${date}</div>
                <div class="timeline-bar" style="height: ${Math.min(100, memories.length * 10)}px">
                    <span class="memory-count">${memories.length}</span>
                </div>
            </div>
        `).join('');
        
        container.innerHTML = `
            <div class="timeline-wrapper">
                ${timelineHTML}
            </div>
        `;
        
        // Add timeline-specific styles
        this.addTimelineStyles();
    }

    addTimelineStyles() {
        if (document.getElementById('timeline-styles')) return;
        
        const styles = `
            <style id="timeline-styles">
                .timeline-wrapper {
                    display: flex;
                    gap: 15px;
                    align-items: flex-end;
                    height: 100%;
                    padding: 20px;
                }
                
                .timeline-day {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 10px;
                    flex: 0 0 auto;
                }
                
                .timeline-date {
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.6);
                    writing-mode: vertical-rl;
                    text-orientation: mixed;
                }
                
                .timeline-bar {
                    width: 30px;
                    background: linear-gradient(to top, rgba(0, 255, 170, 0.3), rgba(0, 255, 170, 0.8));
                    border-radius: 4px;
                    position: relative;
                    cursor: pointer;
                    transition: all 0.3s ease;
                }
                
                .timeline-bar:hover {
                    transform: scaleY(1.1);
                    background: linear-gradient(to top, rgba(0, 255, 170, 0.5), rgba(0, 255, 170, 1));
                }
                
                .memory-count {
                    position: absolute;
                    top: -20px;
                    left: 50%;
                    transform: translateX(-50%);
                    font-size: 10px;
                    color: #00ffaa;
                }
            </style>
        `;
        
        document.head.insertAdjacentHTML('beforeend', styles);
    }

    // ===== Cluster View =====
    showClusterView() {
        if (!this.memoryData) {
            this.loadMemoryData().then(() => this.createClusters());
        } else {
            this.createClusters();
        }
    }

    createClusters() {
        // Use Web Worker for clustering if available
        if (this.worker) {
            this.worker.postMessage({ 
                type: 'calculateClusters', 
                data: this.memoryData 
            });
        } else {
            this.renderClusterViewDirect();
        }
    }

    renderClusterView(clusters) {
        // Create Three.js scene for cluster visualization
        if (!window.THREE) return;
        
        const scene = new THREE.Scene();
        const container = document.getElementById('network-container');
        
        // Clear existing content
        container.innerHTML = '';
        this.addViewControls();
        
        // Create renderer
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        container.appendChild(renderer.domElement);
        
        // Create camera
        const camera = new THREE.PerspectiveCamera(
            75,
            container.clientWidth / container.clientHeight,
            0.1,
            1000
        );
        camera.position.z = 500;
        
        // Add lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);
        
        // Create cluster spheres
        clusters.forEach((cluster, index) => {
            const geometry = new THREE.SphereGeometry(
                20 + cluster.nodes.length * 2,
                32,
                32
            );
            
            const material = new THREE.MeshPhongMaterial({
                color: new THREE.Color().setHSL(index / clusters.length, 0.7, 0.5),
                transparent: true,
                opacity: 0.7
            });
            
            const mesh = new THREE.Mesh(geometry, material);
            mesh.position.set(
                cluster.center.x * 2,
                cluster.center.y * 2,
                Math.random() * 100 - 50
            );
            
            scene.add(mesh);
        });
        
        // Animation loop
        const animate = () => {
            requestAnimationFrame(animate);
            
            // Rotate clusters
            scene.children.forEach(child => {
                if (child instanceof THREE.Mesh) {
                    child.rotation.y += 0.005;
                }
            });
            
            renderer.render(scene, camera);
        };
        
        animate();
        
        // Add cluster info panel
        this.showClusterInfo(clusters);
    }

    showClusterInfo(clusters) {
        const infoHTML = `
            <div class="cluster-info">
                <h3 style="color: #00ffaa; margin: 0 0 15px 0;">Memory Clusters</h3>
                ${clusters.map((cluster, i) => `
                    <div class="cluster-item" style="margin-bottom: 10px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="width: 12px; height: 12px; border-radius: 50%; 
                                background: hsl(${i * 360 / clusters.length}, 70%, 50%);">
                            </div>
                            <span style="color: #fff;">Cluster ${i + 1}</span>
                        </div>
                        <div style="color: rgba(255,255,255,0.6); font-size: 12px; margin-left: 20px;">
                            ${cluster.nodes.length} memories
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        document.getElementById('network-container').insertAdjacentHTML('beforeend', infoHTML);
    }

    // ===== Graph View (Default) =====
    showGraphView() {
        // Restore original Three.js visualization
        const container = document.getElementById('network-container');
        container.innerHTML = '';
        this.addViewControls();
        
        // Re-initialize the original scene
        if (typeof initScene === 'function') {
            initScene();
            loadMemoryGraph(this.uid);
        }
    }
    
    // ===== Keyboard Help Modal =====
    showKeyboardHelp() {
        const helpHTML = `
            <div id="keyboard-help-modal" style="
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(15, 15, 25, 0.98);
                border: 2px solid var(--color-primary);
                border-radius: 16px;
                padding: 30px;
                z-index: 10000;
                max-width: 500px;
                backdrop-filter: blur(10px);
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            ">
                <h2 style="color: var(--color-primary); margin: 0 0 20px 0;">Keyboard Shortcuts</h2>
                <div style="color: #fff; line-height: 2;">
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Esc</kbd> - Return to Graph View</div>
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Ctrl/Cmd + 1</kbd> - Graph View</div>
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Ctrl/Cmd + 2</kbd> - Heat Map View</div>
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Ctrl/Cmd + 3</kbd> - Timeline View</div>
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Ctrl/Cmd + 4</kbd> - Cluster View</div>
                    <div><kbd style="background: rgba(0,255,170,0.2); padding: 3px 8px; border-radius: 4px;">Ctrl/Cmd + H</kbd> - Show This Help</div>
                </div>
                <button onclick="document.getElementById('keyboard-help-modal').remove()" style="
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: var(--color-primary);
                    color: var(--color-background);
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: 600;
                ">Close</button>
            </div>
        `;
        
        // Remove existing modal if present
        const existing = document.getElementById('keyboard-help-modal');
        if (existing) existing.remove();
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', helpHTML);
        
        // Close on Escape
        const closeOnEscape = (e) => {
            if (e.key === 'Escape') {
                document.getElementById('keyboard-help-modal')?.remove();
                document.removeEventListener('keydown', closeOnEscape);
            }
        };
        document.addEventListener('keydown', closeOnEscape);
    }

    // ===== Data Loading =====
    async loadMemoryData() {
        try {
            const response = await fetch('/api/memory-graph', {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                this.memoryData = data.nodes || [];
                return this.memoryData;
            }
        } catch (error) {
            console.error('Error loading memory data:', error);
        }
        
        return [];
    }

    // ===== Cleanup =====
    destroy() {
        if (this.worker) {
            this.worker.terminate();
        }
        
        if (this.virtualScroller) {
            this.virtualScroller.destroy();
        }
        
        if (this.imageLoader) {
            this.imageLoader.destroy();
        }
    }
}

// ===== Virtual Scroller for Performance =====
class VirtualScroller {
    constructor() {
        this.itemHeight = 80;
        this.containerHeight = 600;
        this.items = [];
        this.scrollTop = 0;
        this.visibleItems = [];
    }

    init(container, items) {
        this.container = container;
        this.items = items;
        
        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.style.height = `${this.items.length * this.itemHeight}px`;
        wrapper.style.position = 'relative';
        
        // Add scroll listener
        container.addEventListener('scroll', () => {
            this.handleScroll();
        });
        
        this.render();
    }

    handleScroll() {
        this.scrollTop = this.container.scrollTop;
        this.render();
    }

    render() {
        const startIndex = Math.floor(this.scrollTop / this.itemHeight);
        const endIndex = Math.min(
            startIndex + Math.ceil(this.containerHeight / this.itemHeight) + 1,
            this.items.length
        );
        
        // Clear existing items
        this.container.innerHTML = '';
        
        // Render only visible items
        for (let i = startIndex; i < endIndex; i++) {
            const item = this.createItemElement(this.items[i], i);
            item.style.position = 'absolute';
            item.style.top = `${i * this.itemHeight}px`;
            this.container.appendChild(item);
        }
    }

    createItemElement(item, index) {
        const div = document.createElement('div');
        div.className = 'virtual-item';
        div.innerHTML = `
            <div class="memory-item">
                <span class="memory-index">${index + 1}</span>
                <span class="memory-text">${item.name || item.text || 'Memory'}</span>
            </div>
        `;
        return div;
    }

    destroy() {
        if (this.container) {
            this.container.removeEventListener('scroll', this.handleScroll);
        }
    }
}

// ===== Lazy Image Loader =====
class LazyImageLoader {
    constructor() {
        this.observer = null;
        this.init();
    }

    init() {
        if ('IntersectionObserver' in window) {
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        this.loadImage(entry.target);
                    }
                });
            }, {
                rootMargin: '50px'
            });
        }
    }

    observe(image) {
        if (this.observer) {
            this.observer.observe(image);
        } else {
            // Fallback for older browsers
            this.loadImage(image);
        }
    }

    loadImage(img) {
        const src = img.dataset.src;
        if (!src) return;
        
        // Create new image
        const newImg = new Image();
        newImg.onload = () => {
            img.src = src;
            img.classList.add('loaded');
            
            if (this.observer) {
                this.observer.unobserve(img);
            }
        };
        
        newImg.src = src;
    }

    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
    }
}

// ===== Initialize on load =====
let brainViz;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize visualization manager
    brainViz = new BrainVisualizationManager();
    
    // Make it globally accessible
    window.brainViz = brainViz;
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape key to return to main graph view
        if (e.key === 'Escape') {
            e.preventDefault();
            brainViz.switchView('graph');
            return;
        }
        
        // Ctrl/Cmd + H for help
        if ((e.ctrlKey || e.metaKey) && e.key === 'h') {
            e.preventDefault();
            brainViz.showKeyboardHelp();
            return;
        }
        
        // Number keys with Ctrl/Cmd for view switching
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case '1':
                    e.preventDefault();
                    brainViz.switchView('graph');
                    break;
                case '2':
                    e.preventDefault();
                    brainViz.switchView('heatmap');
                    break;
                case '3':
                    e.preventDefault();
                    brainViz.switchView('timeline');
                    break;
                case '4':
                    e.preventDefault();
                    brainViz.switchView('cluster');
                    break;
            }
        }
    });
});

// ===== Export for use in other scripts =====
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        BrainVisualizationManager,
        VirtualScroller,
        LazyImageLoader
    };
}