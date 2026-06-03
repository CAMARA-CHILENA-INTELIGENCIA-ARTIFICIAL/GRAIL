import { useMemo } from "react";

interface GraphMotifProps {
  show: boolean;
}

interface Point {
  x: number;
  y: number;
  r: number;
}

function buildMotif(): { points: Point[]; edges: [Point, Point][] } {
  let seed = 7;
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
  const points: Point[] = [];
  for (let i = 0; i < 26; i++) {
    points.push({
      x: 80 + rnd() * 940,
      y: 80 + rnd() * 940,
      r: 3 + rnd() * 4,
    });
  }
  const edges: [Point, Point][] = [];
  points.forEach((p, i) => {
    points.slice(i + 1).forEach((q) => {
      const d = Math.hypot(p.x - q.x, p.y - q.y);
      if (d < 200) edges.push([p, q]);
    });
  });
  return { points, edges };
}

export default function GraphMotif({ show }: GraphMotifProps) {
  const { points, edges } = useMemo(buildMotif, []);
  return (
    <div className={`graph-motif ${show ? "show" : ""}`}>
      <svg viewBox="0 0 1100 1100" fill="none">
        <g>
          {edges.map(([a, b], i) => (
            <line key={i} className="gm-edge" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
          ))}
        </g>
        <g>
          {points.map((p, i) => (
            <circle key={i} className="gm-node" cx={p.x} cy={p.y} r={p.r.toFixed(1)} />
          ))}
        </g>
      </svg>
    </div>
  );
}
