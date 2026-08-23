#!/usr/bin/env python3
"""Train the ADP outer-loop model for STM32G474 offline.

The trainer consumes measured transition data and emits:

* a C header with the exact 16x7 actor and 16x8 critic shapes used by the MCU;
* a JSON report containing dataset statistics, hyperparameters, metrics, and
  a CRC32 over the exported float32 tensors.

The MCU must only use a validated, fixed-weight export.  This script never
enables online learning and does not replace hardware validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

STATE_COUNT = 7
HIDDEN_COUNT = 16
DT = 1.0 / 10000.0
DISCOUNT = 0.985
ACTOR_LR = 0.00015
CRITIC_LR = 0.003
WEIGHT_LIMIT = 4.0
REFERENCE_SLEW_A_S = 20000.0
FORMAT_VERSION = 2
MODEL_MAGIC = 0x41445032  # "ADP2"

CSV_FIELDS = (
    "episode",
    "step",
    "vref_v",
    "vin_v",
    "vout_v",
    "iin_a",
    "iout_a",
    "iref_applied_a",
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def activation(value: float) -> float:
    return value / (1.0 + abs(value))


def activation_derivative(value: float) -> float:
    denominator = 1.0 + abs(value)
    return 1.0 / (denominator * denominator)


def make_state(
    vref: float,
    vin: float,
    vout: float,
    iin: float,
    iout: float,
    iref: float,
    previous_error: float,
    ilimit: float,
) -> list[float]:
    if vref <= 1e-3 or ilimit <= 1e-3:
        raise ValueError("vref and ilimit must be positive")
    vout_norm = clamp(vout / vref, 0.0, 2.0)
    error = clamp(1.0 - vout_norm, -1.0, 1.0)
    return [
        clamp(vin / vref, 0.0, 2.0),
        vout_norm,
        error,
        clamp(error - previous_error, -1.0, 1.0),
        clamp(iin / ilimit, -1.0, 1.5),
        clamp(iout / ilimit, -1.0, 1.5),
        clamp(iref / ilimit, 0.0, 1.0),
    ]


def reward(state: list[float], action: float) -> float:
    return -(
        4.0 * state[2] ** 2
        + 0.50 * state[3] ** 2
        + 0.10 * state[4] ** 2
        + 0.15 * state[5] ** 2
        + 0.03 * action**2
    )


def apply_slew(
    command: float,
    previous: float,
    maximum_step: float,
) -> tuple[float, float]:
    delta = command - previous
    limited = clamp(delta, -maximum_step, maximum_step)
    applied = clamp(previous + limited, 0.0, 1.0)
    derivative = (
        1.0
        if -maximum_step < delta < maximum_step and 0.0 < applied < 1.0
        else 0.0
    )
    return applied, derivative


class ActorCritic:
    def __init__(self, rng: random.Random) -> None:
        self.actor_input = [
            [rng.uniform(-0.08, 0.08) for _ in range(STATE_COUNT)]
            for _ in range(HIDDEN_COUNT)
        ]
        self.actor_bias = [0.0] * HIDDEN_COUNT
        self.actor_output = [rng.uniform(-0.08, 0.08) for _ in range(HIDDEN_COUNT)]
        self.actor_output_bias = 0.0
        self.critic_input = [
            [rng.uniform(-0.08, 0.08) for _ in range(STATE_COUNT + 1)]
            for _ in range(HIDDEN_COUNT)
        ]
        self.critic_bias = [0.0] * HIDDEN_COUNT
        self.critic_output = [rng.uniform(-0.08, 0.08) for _ in range(HIDDEN_COUNT)]
        self.critic_output_bias = 0.0

    def actor(
        self, state: list[float]
    ) -> tuple[float, float, list[float], list[float]]:
        sums: list[float] = []
        hidden: list[float] = []
        raw = self.actor_output_bias
        for neuron in range(HIDDEN_COUNT):
            current = self.actor_bias[neuron] + sum(
                state[index] * self.actor_input[neuron][index]
                for index in range(STATE_COUNT)
            )
            sums.append(current)
            hidden.append(activation(current))
            raw += self.actor_output[neuron] * hidden[-1]
        return 0.5 + 0.5 * activation(raw), raw, sums, hidden

    def critic(
        self, state: list[float], action: float
    ) -> tuple[float, list[float], list[float]]:
        sums: list[float] = []
        hidden: list[float] = []
        value = self.critic_output_bias
        for neuron in range(HIDDEN_COUNT):
            current = self.critic_bias[neuron] + sum(
                state[index] * self.critic_input[neuron][index]
                for index in range(STATE_COUNT)
            )
            current += action * self.critic_input[neuron][STATE_COUNT]
            sums.append(current)
            hidden.append(activation(current))
            value += self.critic_output[neuron] * hidden[-1]
        return value, sums, hidden

    def clip(self) -> None:
        for neuron in range(HIDDEN_COUNT):
            self.actor_input[neuron] = [
                clamp(value, -WEIGHT_LIMIT, WEIGHT_LIMIT)
                for value in self.actor_input[neuron]
            ]
            self.critic_input[neuron] = [
                clamp(value, -WEIGHT_LIMIT, WEIGHT_LIMIT)
                for value in self.critic_input[neuron]
            ]
            self.actor_bias[neuron] = clamp(
                self.actor_bias[neuron], -WEIGHT_LIMIT, WEIGHT_LIMIT
            )
            self.critic_bias[neuron] = clamp(
                self.critic_bias[neuron], -WEIGHT_LIMIT, WEIGHT_LIMIT
            )
            self.actor_output[neuron] = clamp(
                self.actor_output[neuron], -WEIGHT_LIMIT, WEIGHT_LIMIT
            )
            self.critic_output[neuron] = clamp(
                self.critic_output[neuron], -WEIGHT_LIMIT, WEIGHT_LIMIT
            )
        self.actor_output_bias = clamp(
            self.actor_output_bias, -WEIGHT_LIMIT, WEIGHT_LIMIT
        )
        self.critic_output_bias = clamp(
            self.critic_output_bias, -WEIGHT_LIMIT, WEIGHT_LIMIT
        )

    def update_critic(
        self,
        state: list[float],
        action: float,
        td_error: float,
        learning_rate: float,
    ) -> None:
        _, sums, hidden = self.critic(state, action)
        step = learning_rate * td_error
        for neuron in range(HIDDEN_COUNT):
            output_weight = self.critic_output[neuron]
            hidden_gradient = output_weight * activation_derivative(sums[neuron])
            self.critic_output[neuron] += step * hidden[neuron]
            self.critic_bias[neuron] += step * hidden_gradient
            for index in range(STATE_COUNT):
                self.critic_input[neuron][index] += (
                    step * hidden_gradient * state[index]
                )
            self.critic_input[neuron][STATE_COUNT] += step * hidden_gradient * action
        self.critic_output_bias += step

    def update_actor(
        self,
        state: list[float],
        previous_applied: float,
        maximum_step: float,
        learning_rate: float,
    ) -> None:
        command, raw, sums, hidden = self.actor(state)
        action, limiter_gradient = apply_slew(
            command, previous_applied, maximum_step
        )
        _, critic_sums, _ = self.critic(state, action)
        dqda = sum(
            self.critic_output[neuron]
            * activation_derivative(critic_sums[neuron])
            * self.critic_input[neuron][STATE_COUNT]
            for neuron in range(HIDDEN_COUNT)
        )
        gradient = (
            clamp(dqda, -10.0, 10.0)
            * limiter_gradient
            * 0.5
            * activation_derivative(raw)
        )
        for neuron in range(HIDDEN_COUNT):
            output_weight = self.actor_output[neuron]
            hidden_gradient = (
                gradient * output_weight * activation_derivative(sums[neuron])
            )
            self.actor_output[neuron] += learning_rate * gradient * hidden[neuron]
            self.actor_bias[neuron] += learning_rate * hidden_gradient
            for index in range(STATE_COUNT):
                self.actor_input[neuron][index] += (
                    learning_rate * hidden_gradient * state[index]
                )
        self.actor_output_bias += learning_rate * gradient

    def tensors(self) -> list[float]:
        values: list[float] = []
        for matrix, vector, output, bias in (
            (
                self.actor_input,
                self.actor_bias,
                self.actor_output,
                self.actor_output_bias,
            ),
            (
                self.critic_input,
                self.critic_bias,
                self.critic_output,
                self.critic_output_bias,
            ),
        ):
            for row in matrix:
                values.extend(row)
            values.extend(vector)
            values.extend(output)
            values.append(bias)
        return values

    def checksum(self) -> int:
        payload = b"".join(struct.pack("<f", float(value)) for value in self.tensors())
        return zlib.crc32(payload) & 0xFFFFFFFF

    def export_header(self, path: Path) -> int:
        checksum = self.checksum()

        def c_float(value: float) -> str:
            text = format(float(value), ".9g")
            if "e" not in text.lower() and "." not in text:
                text += ".0"
            return f"{text}f"

        def c_row(values: list[float]) -> str:
            return ", ".join(c_float(value) for value in values)

        lines = [
            "#ifndef ADP_OUTER_WEIGHTS_H",
            "#define ADP_OUTER_WEIGHTS_H",
            "",
            "#include <stdint.h>",
            "",
            "/* Generated by F4CP/tools/adp_offline_train.py. */",
            "/* Validate on a current-limited bench before increasing power. */",
            f"#define ADP_OUTER_WEIGHTS_MAGIC 0x{MODEL_MAGIC:08X}UL",
            f"#define ADP_OUTER_WEIGHTS_VERSION {FORMAT_VERSION}U",
            f"#define ADP_OUTER_WEIGHTS_STATE_COUNT {STATE_COUNT}U",
            f"#define ADP_OUTER_WEIGHTS_HIDDEN_COUNT {HIDDEN_COUNT}U",
            f"#define ADP_OUTER_WEIGHTS_CHECKSUM 0x{checksum:08X}UL",
            "",
            f"static const float adp_actor_input[{HIDDEN_COUNT}][{STATE_COUNT}] = {{",
        ]
        lines.extend(
            f"    {{{c_row(row)}}}," for row in self.actor_input
        )
        lines.extend(
            [
                "};",
                f"static const float adp_actor_bias[{HIDDEN_COUNT}] = {{{c_row(self.actor_bias)}}};",
                f"static const float adp_actor_output[{HIDDEN_COUNT}] = {{{c_row(self.actor_output)}}};",
                f"static const float adp_actor_output_bias = {c_float(self.actor_output_bias)};",
                f"static const float adp_critic_input[{HIDDEN_COUNT}][{STATE_COUNT + 1}] = {{",
            ]
        )
        lines.extend(
            f"    {{{c_row(row)}}}," for row in self.critic_input
        )
        lines.extend(
            [
                "};",
                f"static const float adp_critic_bias[{HIDDEN_COUNT}] = {{{c_row(self.critic_bias)}}};",
                f"static const float adp_critic_output[{HIDDEN_COUNT}] = {{{c_row(self.critic_output)}}};",
                f"static const float adp_critic_output_bias = {c_float(self.critic_output_bias)};",
                "",
                "#endif",
                "",
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="ascii")
        return checksum


@dataclass(frozen=True)
class Transition:
    episode: str
    state: list[float]
    action: float
    next_state: list[float]
    reward: float


def _episode_sort_key(value: str) -> tuple[int, str]:
    try:
        return 0, f"{int(value):020d}"
    except ValueError:
        return 1, value


def load_csv(path: Path, ilimit: float) -> tuple[list[Transition], dict[str, int]]:
    if ilimit <= 1e-3 or not math.isfinite(ilimit):
        raise ValueError("Ilimit must be a finite value greater than 0")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        missing = [field for field in CSV_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(missing)}")
        rows = list(reader)

    if len(rows) < 2:
        raise ValueError("CSV must contain at least two samples")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        episode = (row.get("episode") or "0").strip()
        if not episode:
            episode = "0"
        try:
            step = int(row["step"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"row {index}: step must be an integer") from exc
        current = {"episode": episode, "step": str(step)}
        for field in CSV_FIELDS[2:]:
            try:
                current[field] = str(finite(float(row[field]), field))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"row {index}: invalid {field}") from exc
        normalized.append(current)

    normalized.sort(
        key=lambda row: (_episode_sort_key(row["episode"]), int(row["step"]))
    )
    transitions: list[Transition] = []
    previous_error: dict[str, float] = {}
    for first, second in zip(normalized, normalized[1:]):
        if first["episode"] != second["episode"]:
            continue
        if int(second["step"]) <= int(first["step"]):
            raise ValueError(
                f"episode {first['episode']}: step must increase strictly"
            )
        episode = first["episode"]
        state = make_state(
            float(first["vref_v"]),
            float(first["vin_v"]),
            float(first["vout_v"]),
            float(first["iin_a"]),
            float(first["iout_a"]),
            float(first["iref_applied_a"]),
            previous_error.get(episode, 0.0),
            ilimit,
        )
        next_state = make_state(
            float(second["vref_v"]),
            float(second["vin_v"]),
            float(second["vout_v"]),
            float(second["iin_a"]),
            float(second["iout_a"]),
            float(second["iref_applied_a"]),
            state[2],
            ilimit,
        )
        previous_error[episode] = state[2]
        action = state[6]
        transitions.append(
            Transition(episode, state, action, next_state, reward(state, action))
        )

    if not transitions:
        raise ValueError("CSV has no adjacent rows within an episode")
    return transitions, {
        "samples": len(normalized),
        "transitions": len(transitions),
        "episodes": len({item["episode"] for item in normalized}),
    }


def cosine_lr(initial: float, epoch: int, total_epochs: int) -> float:
    if total_epochs <= 1:
        return initial
    phase = clamp(epoch / float(total_epochs - 1), 0.0, 1.0)
    return initial * (0.10 + 0.90 * 0.5 * (1.0 + math.cos(math.pi * phase)))


def td_error(net: ActorCritic, transition: Transition, maximum_step: float) -> float:
    next_command, _, _, _ = net.actor(transition.next_state)
    next_action, _ = apply_slew(
        next_command, transition.next_state[6], maximum_step
    )
    next_value, _, _ = net.critic(transition.next_state, next_action)
    old_value, _, _ = net.critic(transition.state, transition.action)
    return transition.reward + DISCOUNT * next_value - old_value


def evaluate(
    net: ActorCritic,
    transitions: list[Transition],
    maximum_step: float,
) -> dict[str, float]:
    errors = [abs(td_error(net, transition, maximum_step)) for transition in transitions]
    actions = [net.actor(transition.state)[0] for transition in transitions]
    return {
        "mean_abs_td": sum(errors) / len(errors),
        "max_abs_td": max(errors),
        "actor_command_min": min(actions),
        "actor_command_max": max(actions),
    }


def train(
    transitions: list[Transition],
    args: argparse.Namespace,
    dataset_stats: dict[str, int],
) -> dict[str, object]:
    rng = random.Random(args.seed)
    episodes = sorted({transition.episode for transition in transitions}, key=_episode_sort_key)
    validation_episode_count = max(1, int(math.ceil(len(episodes) * args.validation_ratio)))
    if len(episodes) > 1:
        validation_episodes = set(episodes[-validation_episode_count:])
        validation_set = [
            transition for transition in transitions if transition.episode in validation_episodes
        ]
        train_set = [
            transition for transition in transitions if transition.episode not in validation_episodes
        ]
        if not train_set:
            train_set, validation_set = transitions[:-1], transitions[-1:]
    else:
        split = max(1, int(len(transitions) * (1.0 - args.validation_ratio)))
        train_set, validation_set = transitions[:split], transitions[split:] or transitions[:1]

    net = ActorCritic(rng)
    maximum_step = clamp(
        REFERENCE_SLEW_A_S * DT / args.ilimit,
        0.0,
        1.0,
    )
    for epoch in range(args.epochs):
        rng.shuffle(train_set)
        actor_lr = cosine_lr(args.actor_lr, epoch, args.epochs)
        critic_lr = cosine_lr(args.critic_lr, epoch, args.epochs)
        for transition in train_set:
            next_command, _, _, _ = net.actor(transition.next_state)
            next_action, _ = apply_slew(
                next_command, transition.next_state[6], maximum_step
            )
            next_value, _, _ = net.critic(transition.next_state, next_action)
            old_value, _, _ = net.critic(transition.state, transition.action)
            td = transition.reward + DISCOUNT * next_value - old_value
            td = clamp(td, -10.0, 10.0)
            net.update_critic(transition.state, transition.action, td, critic_lr)
            net.update_actor(
                transition.state,
                transition.action,
                maximum_step,
                actor_lr,
            )
            net.clip()
        progress_period = max(1, args.epochs // 10)
        if (epoch + 1) % progress_period == 0 or epoch == 0:
            train_metric = evaluate(net, train_set, maximum_step)
            validation_metric = evaluate(net, validation_set, maximum_step)
            print(
                f"epoch {epoch + 1}/{args.epochs}, "
                f"train_abs_td={train_metric['mean_abs_td']:.6f}, "
                f"val_abs_td={validation_metric['mean_abs_td']:.6f}, "
                f"actor_lr={actor_lr:.3g}, critic_lr={critic_lr:.3g}",
                flush=True,
            )

    report: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "model_magic": f"0x{MODEL_MAGIC:08X}",
        "shape": {
            "state_count": STATE_COUNT,
            "hidden_count": HIDDEN_COUNT,
            "critic_input_count": STATE_COUNT + 1,
        },
        "dataset": dataset_stats,
        "split": {
            "train_transitions": len(train_set),
            "validation_transitions": len(validation_set),
            "validation_ratio": args.validation_ratio,
        },
        "hyperparameters": {
            "ilimit_a": args.ilimit,
            "epochs": args.epochs,
            "actor_lr": args.actor_lr,
            "critic_lr": args.critic_lr,
            "seed": args.seed,
            "discount": DISCOUNT,
            "reference_slew_a_s": REFERENCE_SLEW_A_S,
        },
        "metrics": {
            "train": evaluate(net, train_set, maximum_step),
            "validation": evaluate(net, validation_set, maximum_step),
        },
        "checksum": f"0x{net.checksum():08X}",
        "online_training": False,
    }
    checksum = net.export_header(Path(args.output))
    report["checksum"] = f"0x{checksum:08X}"
    report_path = Path(args.report) if args.report else Path(args.output).with_suffix(".json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"weights written to {Path(args.output).resolve()}", flush=True)
    print(f"report written to {report_path.resolve()}", flush=True)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--ilimit", required=True, type=float)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--validation-ratio", type=float, default=0.20)
    parser.add_argument("--actor-lr", type=float, default=ACTOR_LR)
    parser.add_argument("--critic-lr", type=float, default=CRITIC_LR)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.epochs < 1:
        raise SystemExit("--epochs must be at least 1")
    if not 0.0 < args.validation_ratio < 0.5:
        raise SystemExit("--validation-ratio must be in (0, 0.5)")
    if not args.dataset.exists():
        raise SystemExit(f"dataset not found: {args.dataset}")
    try:
        transitions, dataset_stats = load_csv(args.dataset, args.ilimit)
        train(transitions, args, dataset_stats)
    except (OSError, ValueError, OverflowError) as exc:
        print(f"training rejected: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
