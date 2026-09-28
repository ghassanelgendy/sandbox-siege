#!/usr/bin/env python3
"""
Generate looping animated GIFs for Sandbox Siege Architecture and Sequence diagrams.
Renders directly on top of the clean Archify canvas captures.
"""

import math
from PIL import Image, ImageDraw

def render_architecture_gif(output_path: str):
    base = Image.open('/tmp/clean_arch.png')
    orig_w, orig_h = base.size
    target_w = 1200
    target_h = int(orig_h * (target_w / orig_w))
    base = base.resize((target_w, target_h), Image.Resampling.LANCZOS).convert('RGBA')

    scale_w = target_w / orig_w
    scale_h = target_h / orig_h

    def to_canvas(x_svg, y_svg):
        xo = 1.1572 * x_svg + 24.9067
        yo = 1.1667 * y_svg + 26.1526
        return (xo * scale_w, yo * scale_h)

    def interpolate_polyline(points, t):
        lengths = []
        total = 0.0
        for i in range(len(points) - 1):
            dx = points[i+1][0] - points[i][0]
            dy = points[i+1][1] - points[i][1]
            seg_len = math.hypot(dx, dy)
            lengths.append(seg_len)
            total += seg_len
        if total == 0:
            return points[0]
        target = t * total
        acc = 0.0
        for i, seg_len in enumerate(lengths):
            if acc + seg_len >= target or i == len(lengths) - 1:
                seg_t = (target - acc) / seg_len if seg_len > 0 else 0
                x = points[i][0] + seg_t * (points[i+1][0] - points[i][0])
                y = points[i][1] + seg_t * (points[i+1][1] - points[i][1])
                return (x, y)
            acc += seg_len
        return points[-1]

    # Convert polylines to canvas coords
    poly_ci_to_runner = [
        to_canvas(115, 128), to_canvas(115, 178),
        to_canvas(190, 217), to_canvas(466, 217), to_canvas(466, 357), to_canvas(490, 357),
        to_canvas(640, 357), to_canvas(715, 357)
    ]
    poly_llm_cycle = [
        to_canvas(790, 318), to_canvas(790, 128),
        to_canvas(715, 89), to_canvas(640, 89),
        to_canvas(790, 128), to_canvas(790, 318)
    ]
    poly_to_gateway = [
        to_canvas(865, 350), to_canvas(935, 350)
    ]
    poly_to_localstack = [
        to_canvas(1095, 357), to_canvas(1130, 357), to_canvas(1130, 224), to_canvas(1165, 224)
    ]
    poly_to_detectors = [
        to_canvas(1095, 357), to_canvas(1165, 357), to_canvas(1240, 396), to_canvas(1240, 462)
    ]
    poly_to_searxng = [
        to_canvas(1015, 405), to_canvas(1015, 600)
    ]
    poly_score_loop = [
        to_canvas(935, 364), to_canvas(900, 364), to_canvas(900, 639), to_canvas(865, 639),
        to_canvas(715, 639), to_canvas(640, 639),
        to_canvas(490, 639), to_canvas(415, 639),
        to_canvas(340, 600), to_canvas(340, 396)
    ]

    total_frames = 36
    duration_ms = 75 # ~13 fps, 2.7s seamless loop
    frames = []

    def draw_particle(draw, pos, color_rgb, size=4.5):
        cx, cy = pos
        r, g, b = color_rgb
        draw.ellipse([cx-size*2.2, cy-size*2.2, cx+size*2.2, cy+size*2.2], fill=(r, g, b, 40))
        draw.ellipse([cx-size*1.3, cy-size*1.3, cx+size*1.3, cy+size*1.3], fill=(r, g, b, 140))
        draw.ellipse([cx-size*0.7, cy-size*0.7, cx+size*0.7, cy+size*0.7], fill=(255, 255, 255, 255))

    for frame_idx in range(total_frames):
        t_global = frame_idx / total_frames
        
        overlay = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Pulse 1: CI & Run Request (cyan)
        p1 = interpolate_polyline(poly_ci_to_runner, t_global)
        draw_particle(draw, p1, (56, 189, 248), size=4.5)

        # Pulse 2: LLM cascade (violet)
        t_llm = (t_global + 0.3) % 1.0
        p2 = interpolate_polyline(poly_llm_cycle, t_llm)
        draw_particle(draw, p2, (192, 132, 252), size=4.0)

        # Pulse 3: Runner -> Gateway tool interception (emerald)
        t_gw = (t_global + 0.55) % 1.0
        p3 = interpolate_polyline(poly_to_gateway, t_gw)
        draw_particle(draw, p3, (52, 211, 153), size=4.5)

        # Pulse 4: Gateway -> LocalStack L1 IAM (amber)
        t_ls = (t_global + 0.7) % 1.0
        p4 = interpolate_polyline(poly_to_localstack, t_ls)
        draw_particle(draw, p4, (251, 191, 36), size=4.5)

        # Pulse 5: Gateway -> L2 Detectors -> Jev (rose)
        t_det = (t_global + 0.75) % 1.0
        p5 = interpolate_polyline(poly_to_detectors, t_det)
        draw_particle(draw, p5, (251, 113, 133), size=4.5)

        # Pulse 6: Egress guard check (rose)
        t_egress = (t_global + 0.15) % 1.0
        p6 = interpolate_polyline(poly_to_searxng, t_egress)
        draw_particle(draw, p6, (251, 113, 133), size=3.5)

        # Pulse 7: Telemetry & Scoring loop (teal)
        t_score = (t_global + 0.4) % 1.0
        p7 = interpolate_polyline(poly_score_loop, t_score)
        draw_particle(draw, p7, (45, 212, 191), size=4.5)

        frame_img = Image.alpha_composite(base, overlay).convert('RGB')
        frame_paletted = frame_img.quantize(colors=128, method=Image.Resampling.LANCZOS, dither=Image.Dither.NONE)
        frames.append(frame_paletted)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True
    )
    print(f'Wrote {output_path}')


def render_sequence_gif(output_path: str):
    base = Image.open('/tmp/clean_seq.png')
    orig_w, orig_h = base.size
    target_w = 1200
    target_h = int(orig_h * (target_w / orig_w))
    base = base.resize((target_w, target_h), Image.Resampling.LANCZOS).convert('RGBA')

    scale_w = target_w / orig_w
    scale_h = target_h / orig_h

    def to_canvas(x_svg, y_svg):
        xo = 1.2269 * x_svg + 25.6515
        yo = 1.2284 * y_svg + 29.1675
        return (xo * scale_w, yo * scale_h)

    messages = [
        {"id": "probe", "x1": 164, "y1": 170, "x2": 499.33, "y2": 170, "color": (52, 211, 153)},
        {"id": "forward-probe", "x1": 513.33, "y1": 202, "x2": 848.67, "y2": 202, "color": (148, 163, 184)},
        {"id": "deny", "x1": 848.67, "y1": 234, "x2": 513.33, "y2": 234, "color": (251, 113, 133)},
        {"id": "deny-back", "x1": 499.33, "y1": 266, "x2": 164, "y2": 266, "color": (148, 163, 184)},
        {"id": "read-secret", "x1": 164, "y1": 312, "x2": 499.33, "y2": 312, "color": (148, 163, 184)},
        {"id": "secret-back", "x1": 499.33, "y1": 344, "x2": 164, "y2": 344, "color": (148, 163, 184)},
        {"id": "escalate", "x1": 164, "y1": 390, "x2": 499.33, "y2": 390, "color": (52, 211, 153)},
        {"id": "evaluate", "x1": 513.33, "y1": 422, "x2": 1198, "y2": 422, "color": (251, 113, 133)},
        {"id": "trap", "x1": 1198, "y1": 454, "x2": 513.33, "y2": 454, "color": (251, 113, 133)},
        {"id": "retry", "x1": 164, "y1": 500, "x2": 499.33, "y2": 500, "color": (52, 211, 153)},
        {"id": "forward-retry", "x1": 513.33, "y1": 532, "x2": 848.67, "y2": 532, "color": (148, 163, 184)},
        {"id": "allow", "x1": 848.67, "y1": 564, "x2": 513.33, "y2": 564, "color": (251, 113, 133)},
        {"id": "rows-back", "x1": 499.33, "y1": 596, "x2": 164, "y2": 596, "color": (148, 163, 184)},
    ]

    # Give each message 3 sub-frames, plus a 4-frame pause at the end
    frames_per_msg = 3
    tail_pause_frames = 4
    total_frames = len(messages) * frames_per_msg + tail_pause_frames
    duration_ms = 85
    frames = []

    def draw_particle(draw, pos, color_rgb, size=4.5):
        cx, cy = pos
        r, g, b = color_rgb
        draw.ellipse([cx-size*2.0, cy-size*2.0, cx+size*2.0, cy+size*2.0], fill=(r, g, b, 45))
        draw.ellipse([cx-size*1.2, cy-size*1.2, cx+size*1.2, cy+size*1.2], fill=(r, g, b, 140))
        draw.ellipse([cx-size*0.6, cy-size*0.6, cx+size*0.6, cy+size*0.6], fill=(255, 255, 255, 255))

    for frame_idx in range(total_frames):
        overlay = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if frame_idx < len(messages) * frames_per_msg:
            msg_idx = frame_idx // frames_per_msg
            sub_step = frame_idx % frames_per_msg
            sub_t = (sub_step + 0.5) / frames_per_msg

            m = messages[msg_idx]
            p_start = to_canvas(m["x1"], m["y1"])
            p_end = to_canvas(m["x2"], m["y2"])
            
            curr_x = p_start[0] + sub_t * (p_end[0] - p_start[0])
            curr_y = p_start[1] + sub_t * (p_end[1] - p_start[1])

            # Draw leading beam trail
            beam_start_x = p_start[0] + max(0, sub_t - 0.35) * (p_end[0] - p_start[0])
            beam_start_y = p_start[1] + max(0, sub_t - 0.35) * (p_end[1] - p_start[1])
            r, g, b = m["color"]
            draw.line([beam_start_x, beam_start_y, curr_x, curr_y], fill=(r, g, b, 200), width=3)

            # Draw intense leading particle
            draw_particle(draw, (curr_x, curr_y), m["color"], size=4.5)

            # Ripple effect on arrival (sub_step == 0 if msg_idx > 0)
            if sub_step == 0 and msg_idx > 0:
                prev_m = messages[msg_idx - 1]
                prev_end = to_canvas(prev_m["x2"], prev_m["y2"])
                pr, pg, pb = prev_m["color"]
                draw.ellipse([prev_end[0]-10, prev_end[1]-10, prev_end[0]+10, prev_end[1]+10], outline=(pr, pg, pb, 160), width=2)
        else:
            # During final pause, show a pulse at the final destination
            last_m = messages[-1]
            last_end = to_canvas(last_m["x2"], last_m["y2"])
            draw_particle(draw, last_end, last_m["color"], size=4.0)

        frame_img = Image.alpha_composite(base, overlay).convert('RGB')
        frame_paletted = frame_img.quantize(colors=128, method=Image.Resampling.LANCZOS, dither=Image.Dither.NONE)
        frames.append(frame_paletted)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True
    )
    print(f'Wrote {output_path}')


if __name__ == '__main__':
    render_architecture_gif('assets/siege-architecture-animated.gif')
    render_sequence_gif('assets/siege-l1-l2-sequence-animated.gif')
