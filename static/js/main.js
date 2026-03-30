/**
 * EYE-FONCIER — Scripts Principaux v5
 * Plateforme WebSIG de Transaction Fonciere Securisee
 * Design System v5 — Sand Theme + Orange CTA + Kente Pattern
 */

'use strict';

const EyeFoncier = {
    config: {
        apiBase: '/api/v1',
        mapCenter: [5.36, -4.008],
        mapZoom: 13,
        statusColors: {
            disponible: '#059669',
            reserve: '#D97706',
            vendu: '#DC2626'
        }
    },

    init() {
        this.initTooltips();
        this.initAlertDismiss();
        this.initSmoothScroll();
        this.initFormValidation();
        this.initScrollReveal();
        this.initFormEnhancements();
        this.initLoadingStates();
        this.initNavActiveState();
        console.log('EYE-FONCIER v5 initialized');
    },

    // ===== Bootstrap Tooltips =====
    initTooltips() {
        if (typeof bootstrap === 'undefined') return;
        document.querySelectorAll('[data-bs-toggle="tooltip"]')
            .forEach(el => new bootstrap.Tooltip(el));
    },

    // ===== Auto-dismiss alerts =====
    initAlertDismiss() {
        document.querySelectorAll('.alert-auto-dismiss').forEach(alert => {
            setTimeout(() => {
                if (typeof bootstrap !== 'undefined') {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    bsAlert.close();
                } else {
                    alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
                    alert.style.opacity = '0';
                    alert.style.transform = 'translateY(-10px)';
                    setTimeout(() => alert.remove(), 400);
                }
            }, 5000);
        });
    },

    // ===== Smooth scroll =====
    initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                if (href === '#') return;
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });
    },

    // ===== Client-side form validation =====
    initFormValidation() {
        document.querySelectorAll('form[data-validate]').forEach(form => {
            form.addEventListener('submit', function(e) {
                if (!form.checkValidity()) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
    },

    // ===== Scroll Reveal Animations =====
    initScrollReveal() {
        // Auto-apply to common v5 elements
        const selectors = [
            '.ef-card',
            '.ef-stat-card',
            '.ef-alert-card',
            '.ef-empty-state',
            '.ef-section-hero',
            '.ef-page-header',
            '.animate-on-scroll'
        ];

        const elements = document.querySelectorAll(selectors.join(','));
        if (!elements.length) return;

        // Skip elements that are above the fold (already visible)
        const viewportHeight = window.innerHeight;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Stagger delay based on position in a row
                    const siblings = entry.target.parentElement
                        ? Array.from(entry.target.parentElement.children).filter(el => el.matches(selectors.join(',')))
                        : [];
                    const index = siblings.indexOf(entry.target);
                    const delay = Math.min(index * 60, 300);

                    setTimeout(() => {
                        entry.target.classList.add('ef-revealed');
                    }, delay);
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.08,
            rootMargin: '0px 0px -30px 0px'
        });

        elements.forEach(el => {
            // Don't animate elements already in the viewport at page load
            const rect = el.getBoundingClientRect();
            if (rect.top < viewportHeight * 0.85) {
                el.classList.add('ef-revealed');
                return;
            }
            el.classList.add('ef-reveal-ready');
            observer.observe(el);
        });
    },

    // ===== Form Enhancements =====
    initFormEnhancements() {
        // Auto-add ef-input class to form controls inside .ef-form-group
        document.querySelectorAll('.ef-form-group input, .ef-form-group select, .ef-form-group textarea').forEach(el => {
            if (!el.classList.contains('form-check-input') && !el.classList.contains('ef-input')) {
                el.classList.add('ef-input');
            }
        });

        // Password visibility toggle
        document.querySelectorAll('[data-toggle-password]').forEach(btn => {
            btn.addEventListener('click', function() {
                const input = document.querySelector(this.dataset.togglePassword);
                if (input) {
                    const isPassword = input.type === 'password';
                    input.type = isPassword ? 'text' : 'password';
                    const icon = this.querySelector('i');
                    if (icon) {
                        icon.className = isPassword ? 'bi bi-eye-slash' : 'bi bi-eye';
                    }
                }
            });
        });

        // Auto-format FCFA price inputs
        document.querySelectorAll('[data-format="fcfa"]').forEach(input => {
            input.addEventListener('blur', function() {
                const val = parseInt(this.value.replace(/\D/g, ''));
                if (!isNaN(val)) {
                    this.value = new Intl.NumberFormat('fr-FR').format(val);
                }
            });
            input.addEventListener('focus', function() {
                this.value = this.value.replace(/\s/g, '');
            });
        });
    },

    // ===== Loading States =====
    initLoadingStates() {
        // Add loading spinner to submit buttons on form submit
        document.querySelectorAll('form').forEach(form => {
            // Skip forms with file uploads (they have their own handling)
            if (form.querySelector('input[type="file"]')) return;
            // Skip small inline forms (like logout)
            if (form.querySelectorAll('input, select, textarea').length < 2) return;

            form.addEventListener('submit', function() {
                const btn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (btn && !btn.disabled) {
                    btn.disabled = true;
                    const originalContent = btn.innerHTML;
                    btn.dataset.originalContent = originalContent;
                    btn.innerHTML = '<span class="ef-spinner"></span> Chargement...';
                    btn.style.opacity = '0.7';
                    btn.style.pointerEvents = 'none';

                    // Safety: re-enable after 10s in case of error
                    setTimeout(() => {
                        btn.disabled = false;
                        btn.innerHTML = originalContent;
                        btn.style.opacity = '';
                        btn.style.pointerEvents = '';
                    }, 10000);
                }
            });
        });
    },

    // ===== Nav Active State =====
    initNavActiveState() {
        // Highlight active mobile nav link
        const currentPath = window.location.pathname;
        document.querySelectorAll('.ef-mobile-nav-link').forEach(link => {
            if (link.getAttribute('href') === currentPath) {
                link.style.background = 'var(--green-50)';
                link.style.color = 'var(--green-900)';
                link.style.fontWeight = '600';
            }
        });
    },

    // ===== API Helper =====
    async apiRequest(endpoint, options = {}) {
        const url = this.config.apiBase + endpoint;
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            }
        };
        const config = { ...defaults, ...options };
        try {
            const response = await fetch(url, config);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            this.showToast('Erreur de connexion au serveur', 'danger');
            throw error;
        }
    },

    // ===== CSRF Token =====
    getCSRFToken() {
        const cookie = document.cookie.split(';')
            .find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    },

    // ===== Format prix FCFA =====
    formatPrice(amount) {
        return new Intl.NumberFormat('fr-FR', {
            style: 'decimal',
            maximumFractionDigits: 0
        }).format(amount) + ' FCFA';
    },

    // ===== Format surface =====
    formatSurface(m2) {
        if (m2 >= 10000) {
            return (m2 / 10000).toFixed(2) + ' ha';
        }
        return new Intl.NumberFormat('fr-FR').format(m2) + ' m\u00B2';
    },

    // ===== MapLibre GL JS helpers =====
    mapStyles: {
        satellite: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'esri-satellite': { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 19, attribution: 'Esri' } },
            layers: [{ id: 'satellite', type: 'raster', source: 'esri-satellite' }]
        },
        streets: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'carto': { type: 'raster', tiles: ['https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png', 'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png', 'https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png'], tileSize: 256, maxzoom: 20, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>' } },
            layers: [{ id: 'streets', type: 'raster', source: 'carto' }]
        },
        topo: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'esri-topo': { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 19, attribution: 'Esri' } },
            layers: [{ id: 'topo', type: 'raster', source: 'esri-topo' }]
        },
        dark: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'carto-dark': { type: 'raster', tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png', 'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png', 'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'], tileSize: 256, maxzoom: 20, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>' } },
            layers: [{ id: 'dark', type: 'raster', source: 'carto-dark' }]
        },
        positron: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'carto-positron': { type: 'raster', tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png', 'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png', 'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png'], tileSize: 256, maxzoom: 20, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>' } },
            layers: [{ id: 'positron', type: 'raster', source: 'carto-positron' }]
        },
        watercolor: {
            version: 8,
            glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
            sources: { 'stamen-watercolor': { type: 'raster', tiles: ['https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg'], tileSize: 256, maxzoom: 18, attribution: '&copy; <a href="https://stadiamaps.com/">Stadia</a> &copy; <a href="https://stamen.com/">Stamen</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>' } },
            layers: [{ id: 'watercolor', type: 'raster', source: 'stamen-watercolor' }]
        }
    },

    map: {
        getStatusColor(status) {
            return EyeFoncier.config.statusColors[status] || '#6b7280';
        },

        /** Match expression for MapLibre data-driven styling */
        statusColorExpr() {
            return ['match', ['get', 'status'],
                'disponible', '#059669',
                'reserve', '#D97706',
                'vendu', '#DC2626',
                '#6b7280'
            ];
        },

        createPopupContent(props) {
            return `
                <div style="min-width:220px;">
                    <div class="popup-title">${props.title || 'Parcelle'}</div>
                    <div class="popup-surface">
                        <i class="bi bi-arrows-fullscreen"></i> ${EyeFoncier.formatSurface(props.surface_m2)}
                        &middot; Lot ${props.lot_number || '\u2014'}
                    </div>
                    <div class="popup-price mt-1">${EyeFoncier.formatPrice(props.price)}</div>
                    <hr style="margin:.5rem 0;">
                    <a href="/parcelles/${props.id}/" class="btn btn-success btn-sm w-100" style="border-radius:50px">
                        <i class="bi bi-eye me-1"></i> Voir d\u00E9tails
                    </a>
                </div>
            `;
        },

        /** Compute centroids from GeoJSON polygon features → Point FeatureCollection */
        computeCentroids(features) {
            const points = [];
            features.forEach(function(f) {
                if (!f.geometry) return;
                const coords = f.geometry.coordinates;
                let cx = 0, cy = 0, n = 0;
                if (f.geometry.type === 'Polygon' && coords[0]) {
                    coords[0].forEach(function(c) { cx += c[0]; cy += c[1]; n++; });
                } else if (f.geometry.type === 'MultiPolygon' && coords[0] && coords[0][0]) {
                    coords[0][0].forEach(function(c) { cx += c[0]; cy += c[1]; n++; });
                }
                if (n > 0) {
                    points.push({ type: 'Feature', id: f.id, properties: f.properties, geometry: { type: 'Point', coordinates: [cx / n, cy / n] } });
                }
            });
            return { type: 'FeatureCollection', features: points };
        },

        /** Enable 2.5D/3D mode with smooth animation */
        enable3D(mapInstance) {
            mapInstance.easeTo({ pitch: 55, bearing: -15, duration: 1000 });
        },

        /** Disable 3D mode — return to flat 2D */
        disable3D(mapInstance) {
            mapInstance.easeTo({ pitch: 0, bearing: 0, duration: 1000 });
        },

        /** Compute LngLatBounds from GeoJSON features */
        getBoundsFromFeatures(features) {
            const bounds = new maplibregl.LngLatBounds();
            features.forEach(function(f) {
                if (!f.geometry) return;
                const coords = f.geometry.coordinates;
                if (f.geometry.type === 'Polygon' && coords[0]) {
                    coords[0].forEach(function(c) { bounds.extend(c); });
                } else if (f.geometry.type === 'MultiPolygon') {
                    coords.forEach(function(poly) { if (poly[0]) poly[0].forEach(function(c) { bounds.extend(c); }); });
                } else if (f.geometry.type === 'Point') {
                    bounds.extend(coords);
                }
            });
            return bounds;
        },

        /** Add parcelle polygon layers to a MapLibre map (simple helper for detail/validate pages) */
        addParcelleGeoJSON(mapInstance, geojson, opts) {
            opts = opts || {};
            const sourceId = opts.sourceId || 'parcelle';
            const fillColor = opts.fillColor || '#22c55e';
            const lineColor = opts.lineColor || '#E8793B';

            mapInstance.addSource(sourceId, {
                type: 'geojson',
                data: { type: 'Feature', geometry: geojson, properties: {} }
            });
            mapInstance.addLayer({
                id: sourceId + '-fill', type: 'fill', source: sourceId,
                paint: { 'fill-color': fillColor, 'fill-opacity': 0.2 }
            });
            mapInstance.addLayer({
                id: sourceId + '-line', type: 'line', source: sourceId,
                paint: { 'line-color': lineColor, 'line-width': 3 }
            });

            // Fit bounds
            const bounds = new maplibregl.LngLatBounds();
            function extendBounds(coords) {
                if (typeof coords[0] === 'number') { bounds.extend(coords); return; }
                coords.forEach(function(c) { extendBounds(c); });
            }
            extendBounds(geojson.coordinates);
            if (!bounds.isEmpty()) {
                mapInstance.fitBounds(bounds, { padding: opts.padding || 30 });
            }
        },

        async loadParcelles(mapInstance, params = {}) {
            const query = new URLSearchParams(params).toString();
            const url = `/api/v1/parcelles/geojson/${query ? '?' + query : ''}`;
            try {
                const response = await fetch(url);
                const data = await response.json();

                // Remove old layers/source if they exist
                ['parcelles-fill', 'parcelles-line'].forEach(function(lid) {
                    if (mapInstance.getLayer(lid)) mapInstance.removeLayer(lid);
                });
                if (mapInstance.getSource('parcelles')) mapInstance.removeSource('parcelles');

                mapInstance.addSource('parcelles', { type: 'geojson', data: data });
                const colorExpr = EyeFoncier.map.statusColorExpr();
                mapInstance.addLayer({
                    id: 'parcelles-fill', type: 'fill', source: 'parcelles',
                    paint: { 'fill-color': colorExpr, 'fill-opacity': 0.25 }
                });
                mapInstance.addLayer({
                    id: 'parcelles-line', type: 'line', source: 'parcelles',
                    paint: { 'line-color': colorExpr, 'line-width': 2.5, 'line-opacity': 0.9 }
                });

                // Popup on click
                mapInstance.on('click', 'parcelles-fill', function(e) {
                    if (e.features.length > 0) {
                        const props = e.features[0].properties;
                        new maplibregl.Popup({ maxWidth: '280px' })
                            .setLngLat(e.lngLat)
                            .setHTML(EyeFoncier.map.createPopupContent(props))
                            .addTo(mapInstance);
                    }
                });
                mapInstance.on('mouseenter', 'parcelles-fill', function() { mapInstance.getCanvas().style.cursor = 'pointer'; });
                mapInstance.on('mouseleave', 'parcelles-fill', function() { mapInstance.getCanvas().style.cursor = ''; });

                return data;
            } catch (error) {
                console.error('Error loading parcelles:', error);
                return null;
            }
        }
    },

    // ===== Toast Notifications (Design System v5) =====
    showToast(message, type = 'success') {
        // Create toast container if not exists
        let container = document.getElementById('ef-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'ef-toast-container';
            container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column-reverse;gap:8px;max-width:380px;width:calc(100vw - 48px)';
            document.body.appendChild(container);
        }

        const icons = {
            success: 'check-circle-fill',
            danger: 'exclamation-triangle-fill',
            warning: 'exclamation-circle-fill',
            info: 'info-circle-fill'
        };
        const colors = {
            success: { bg: 'var(--green-900)', border: 'var(--green-700)' },
            danger: { bg: '#991B1B', border: 'var(--danger)' },
            warning: { bg: '#92400E', border: 'var(--warning)' },
            info: { bg: '#1E40AF', border: 'var(--blue)' }
        };
        const c = colors[type] || colors.success;

        const toast = document.createElement('div');
        toast.style.cssText = `
            display:flex;align-items:center;gap:10px;padding:14px 18px;
            background:${c.bg};color:var(--white);
            border-radius:var(--radius-md);box-shadow:var(--shadow-lg);
            font-family:var(--font-body);font-size:.88rem;
            border-left:4px solid ${c.border};
            transform:translateX(110%);opacity:0;
            transition:all 0.4s cubic-bezier(0.4,0,0.2,1);
            cursor:pointer;
        `;
        toast.innerHTML = `
            <i class="bi bi-${icons[type] || 'info-circle-fill'}" style="font-size:1.1rem;flex-shrink:0"></i>
            <span style="flex:1">${message}</span>
            <i class="bi bi-x-lg" style="font-size:.75rem;opacity:.6;flex-shrink:0"></i>
        `;

        container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                toast.style.transform = 'translateX(0)';
                toast.style.opacity = '1';
            });
        });

        // Click to dismiss
        toast.addEventListener('click', () => dismissToast(toast));

        // Auto-dismiss after 4s
        const timeout = setTimeout(() => dismissToast(toast), 4000);

        function dismissToast(el) {
            clearTimeout(timeout);
            el.style.transform = 'translateX(110%)';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        }
    },

    // ===== Confirmation Dialog =====
    confirm(message, onConfirm) {
        // Create a v5-styled modal confirmation
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9998;background:rgba(11,61,46,0.4);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:20px;animation:ef-fade-in 0.2s ease';

        const card = document.createElement('div');
        card.style.cssText = 'background:var(--white);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);max-width:400px;width:100%;padding:2rem;text-align:center;animation:ef-scale-in 0.25s ease';
        card.innerHTML = `
            <i class="bi bi-question-circle" style="font-size:3rem;color:var(--warning);margin-bottom:1rem;display:block"></i>
            <h5 style="font-family:var(--font-display);font-weight:700;color:var(--green-900);margin-bottom:.5rem">Confirmation</h5>
            <p style="color:var(--gray-600);font-size:.92rem;margin-bottom:1.5rem">${message}</p>
            <div style="display:flex;gap:10px;justify-content:center">
                <button class="ef-btn ef-btn-ghost" id="ef-confirm-cancel" style="min-width:100px">Annuler</button>
                <button class="ef-btn ef-btn-primary" id="ef-confirm-ok" style="min-width:100px">Confirmer</button>
            </div>
        `;

        overlay.appendChild(card);
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const cleanup = () => {
            document.body.style.overflow = '';
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 200);
        };

        card.querySelector('#ef-confirm-cancel').addEventListener('click', cleanup);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(); });
        card.querySelector('#ef-confirm-ok').addEventListener('click', () => {
            cleanup();
            if (onConfirm) onConfirm();
        });
    }
};

// ===== Auto-init =====
document.addEventListener('DOMContentLoaded', () => EyeFoncier.init());
