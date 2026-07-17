// Renders a live orrery-style wheel: zodiac ring + planet glyphs positioned
// by real ecliptic longitude. This is the dashboard's signature element --
// an actual instrument reading, not a decorative chart.

const ZODIAC_GLYPHS = ["♈","♉","♊","♋","♌","♍","♎","♏","♐","♑","♒","♓"];
const PLANET_GLYPHS = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Rahu: "☊", Ketu: "☋",
};

function renderZodiacWheel(containerEl, positions) {
  const size = 480;
  const cx = size / 2, cy = size / 2;
  const outerR = 220, signRingR = 195, planetR = 155;

  let svg = `<svg viewBox="0 0 ${size} ${size}" class="orrery">`;

  // Outer rim
  svg += `<circle cx="${cx}" cy="${cy}" r="${outerR}" class="orrery-rim" />`;
  svg += `<circle cx="${cx}" cy="${cy}" r="${signRingR}" class="orrery-ring" />`;
  svg += `<circle cx="${cx}" cy="${cy}" r="${planetR - 28}" class="orrery-core" />`;

  // 12 sign divisions + glyphs
  for (let i = 0; i < 12; i++) {
    const startDeg = i * 30;
    const midDeg = startDeg + 15;
    const rad1 = (startDeg - 90) * Math.PI / 180;
    const x1 = cx + outerR * Math.cos(rad1);
    const y1 = cy + outerR * Math.sin(rad1);
    const x2 = cx + (planetR - 28) * Math.cos(rad1);
    const y2 = cy + (planetR - 28) * Math.sin(rad1);
    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="orrery-spoke" />`;

    const radMid = (midDeg - 90) * Math.PI / 180;
    const gx = cx + signRingR * Math.cos(radMid);
    const gy = cy + signRingR * Math.sin(radMid);
    svg += `<text x="${gx}" y="${gy}" class="orrery-sign-glyph" text-anchor="middle" dominant-baseline="central">${ZODIAC_GLYPHS[i]}</text>`;
  }

  // Planets at real longitude
  Object.entries(positions || {}).forEach(([planet, data], idx) => {
    const rad = (data.longitude - 90) * Math.PI / 180;
    const r = planetR - (idx % 3) * 14; // slight stagger so close planets don't overlap
    const px = cx + r * Math.cos(rad);
    const py = cy + r * Math.sin(rad);
    const retro = data.is_retrograde ? " (R)" : "";
    svg += `<g class="orrery-planet">
      <circle cx="${px}" cy="${py}" r="14" class="orrery-planet-dot ${data.is_retrograde ? 'retrograde' : ''}" />
      <text x="${px}" y="${py}" class="orrery-planet-glyph" text-anchor="middle" dominant-baseline="central">${PLANET_GLYPHS[planet] || "?"}</text>
      <title>${planet}${retro} in ${data.sign} ${data.degree_in_sign}°</title>
    </g>`;
  });

  svg += `</svg>`;
  containerEl.innerHTML = svg;
}
