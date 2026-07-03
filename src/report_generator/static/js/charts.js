/**
 * OSINT BBW Tool v2.0 – 3D SVG Charts
 * Vanilla JavaScript – keine Frameworks, keine Abhängigkeiten.
 *
 * Features:
 *   - 3D-Donut-Chart mit SVG-RadialGradient & DropShadow
 *   - Animierte stroke-dashoffset-Transition
 *   - Plattform-Donut mit Segment-Gradienten
 *   - KEINE SVG-transform (WeasyPrint-kompatibel)
 *
 * Autor: Rayquaza, 2026
 */

function darkenColor(hex, factor) {
  var r = parseInt(hex.slice(1,3), 16);
  var g = parseInt(hex.slice(3,5), 16);
  var b = parseInt(hex.slice(5,7), 16);
  r = Math.floor(r * (1 - factor));
  g = Math.floor(g * (1 - factor));
  b = Math.floor(b * (1 - factor));
  return '#' + [r,g,b].map(function(c){return c.toString(16).padStart(2,'0')}).join('');
}

/**
 * 3D-Risiko-Donut-Chart – KEINE SVG-transform!
 *
 * Mathematik:
 *   Kreisumfang C = 2 × π × 85 = 534.071
 *   dashoffset = C × (1 - percentage/100)  → sichtbarer Anteil ab 3-Uhr
 *   Für Start bei 12-Uhr: finalOffset = (offset + C × 0.25) % C
 *   C × 0.25 = 90°-Rotation als dashoffset-Versatz
 */
function drawRiskCircle3D(elementId, percentage, color) {
  var el = document.getElementById(elementId);
  if (!el) return;
  percentage = Math.max(0, Math.min(100, Math.round(percentage || 0)));
  var strokeColor = color || '#f97316';
  var darker = darkenColor(strokeColor, 0.4);

  // Kreisumfang: 2 × π × r = 2 × 3.14159 × 85 ≈ 534.07
  var circumference = 2 * Math.PI * 85;
  // Sichtbarer Anteil (ab 3-Uhr-Position)
  var offset = circumference * (1 - percentage / 100);
  // Start bei 12-Uhr: 90°-Versatz = circumference / 4
  var startOffset = circumference * 0.25;
  var finalOffset = (startOffset + offset) % circumference;

  var svg = '<svg viewBox="0 0 200 200" width="200" height="200" class="risk-circle-svg" role="img">';
  svg += '<defs>';
  svg += '<radialGradient id="rg3d" cx="40%" cy="35%" r="60%">';
  svg += '<stop offset="0%" stop-color="' + strokeColor + '" stop-opacity="1"/>';
  svg += '<stop offset="100%" stop-color="' + darker + '" stop-opacity="1"/>';
  svg += '</radialGradient>';
  svg += '<filter id="sh3d"><feDropShadow dx="3" dy="5" stdDeviation="5" flood-opacity="0.3"/></filter>';
  svg += '</defs>';
  // Hintergrund-Ring
  svg += '<circle cx="100" cy="100" r="85" fill="none" stroke="#e2e8f0" stroke-width="16"/>';
  // Farbiger Vordergrund-Ring – KEIN transform!
  svg += '<circle cx="100" cy="100" r="85" fill="none" stroke="url(#rg3d)" stroke-width="16" stroke-linecap="round"';
  svg += ' stroke-dasharray="' + circumference.toFixed(1) + '" stroke-dashoffset="' + finalOffset.toFixed(1) + '"';
  svg += ' filter="url(#sh3d)"';
  svg += ' style="transition: stroke-dashoffset 2s ease-out;"/>';
  // Donut-Loch
  svg += '<circle cx="100" cy="100" r="65" fill="var(--bg-card, white)" stroke="#e0e0e0" stroke-width="1"/>';
  svg += '<text x="100" y="92" text-anchor="middle" font-size="38" font-weight="900" fill="' + strokeColor + '">' + percentage + '%</text>';
  svg += '<text x="100" y="118" text-anchor="middle" font-size="12" font-weight="600" fill="#94a3b8">RISIKO</text>';
  svg += '</svg>';
  el.innerHTML = svg;
}

/**
 * 3D-Plattform-Donut-Chart – KEINE SVG-transform!
 * Segmente werden über Math.cos/sin berechnet, kein rotate nötig.
 */
function drawPlatformChart3D(elementId, platforms) {
  var el = document.getElementById(elementId);
  if (!el || !platforms || !platforms.length) {
    if (el) el.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">Keine Daten</div>';
    return;
  }

  var cx = 100, cy = 100, r = 80;
  var svg = '<svg viewBox="0 0 200 200" width="240" height="240" class="platform-chart-svg" role="img">';
  svg += '<defs><filter id="psh3d"><feDropShadow dx="2" dy="3" stdDeviation="3" flood-opacity="0.25"/></filter></defs>';

  // Start bei 12-Uhr: -PI/2
  var cumAngle = -Math.PI / 2;
  for (var i = 0; i < platforms.length; i++) {
    var pct = platforms[i].percentage || 0;
    var color = platforms[i].color || '#6b7280';
    var angle = (pct / 100) * 2 * Math.PI;
    var startAngle = cumAngle;
    var endAngle = startAngle + angle;
    var x1 = cx + r * Math.cos(startAngle);
    var y1 = cy + r * Math.sin(startAngle);
    var x2 = cx + r * Math.cos(endAngle);
    var y2 = cy + r * Math.sin(endAngle);
    var large = pct > 50 ? 1 : 0;
    var d = 'M ' + cx + ' ' + cy + ' L ' + x1.toFixed(1) + ' ' + y1.toFixed(1) +
            ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2.toFixed(1) + ' ' + y2.toFixed(1) + ' Z';
    svg += '<path d="' + d + '" fill="' + color + '" stroke="white" stroke-width="2" filter="url(#psh3d)" opacity="0.9">';
    svg += '<title>' + (platforms[i].label || '?') + ': ' + pct + '%</title></path>';
    cumAngle = endAngle;
  }
  svg += '<circle cx="100" cy="100" r="45" fill="var(--bg-card, white)" stroke="#e0e0e0" stroke-width="1"/>';
  svg += '<text x="100" y="96" text-anchor="middle" font-size="18" font-weight="800" fill="var(--text-primary)">' + platforms.length + '</text>';
  svg += '<text x="100" y="114" text-anchor="middle" font-size="9" font-weight="600" fill="#94a3b8">KATEGORIEN</text>';
  svg += '</svg>';

  var legend = '<div class="platform-legend" style="margin-top:16px;">';
  for (var j = 0; j < platforms.length; j++) {
    var p = platforms[j];
    legend += '<div class="platform-item">';
    if (p.logo) {
      legend += '<img src="' + p.logo + '" class="platform-logo" style="width:24px;height:24px;border-radius:4px;margin-right:8px;" alt="">';
    } else {
      legend += '<span class="color-dot" style="background:' + (p.color || '#6b7280') + ';"></span>';
    }
    legend += '<span class="platform-name">' + (p.label || '?') + '</span>';
    legend += '<span class="platform-count">' + (p.percentage || 0) + '%</span>';
    legend += '</div>';
  }
  legend += '</div>';
  el.innerHTML = svg + legend;
}

document.addEventListener('DOMContentLoaded', function() {
  var riskEl = document.getElementById('risk-circle');
  if (riskEl) {
    var score = parseInt(riskEl.getAttribute('data-risk-score'), 10) || 0;
    var color = riskEl.getAttribute('data-risk-color') || '#f97316';
    drawRiskCircle3D('risk-circle', score, color);
  }
  var platEl = document.getElementById('platform-chart');
  if (platEl) {
    try {
      var data = JSON.parse(platEl.getAttribute('data-categories') || '[]');
      drawPlatformChart3D('platform-chart', data);
    } catch(e) { console.warn('Chart data parse error:', e); }
  }
});
