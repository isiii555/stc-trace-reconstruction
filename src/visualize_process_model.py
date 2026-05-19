from pathlib import Path

import pandas as pd


INPUT_PATH = Path("out/eventlog_STC_v2_history_ip_delta5s.csv")
BPMN_PNG_PATH = Path("out/process_model_STC_delta5_bpmn.png")
BPMN_SVG_PATH = Path("out/process_model_STC_delta5_bpmn.svg")
PETRI_PNG_PATH = Path("out/process_model_STC_delta5_petri.png")
PETRI_SVG_PATH = Path("out/process_model_STC_delta5_petri.svg")

CASE_COL = "case_id"
ACT_COL = "activity"
TIME_COL = "timestamp"

MAX_CASES = 30
MAX_EVENTS = 300
MAX_EVENTS_PER_CASE = 10


def load_small_sample() -> pd.DataFrame | None:
    if not INPUT_PATH.exists():
        print(f"Input event log not found: {INPUT_PATH}")
        print("Run the HDFS demo first, then try this optional visualization again.")
        return None

    df = pd.read_csv(INPUT_PATH, low_memory=False)
    missing = [col for col in [CASE_COL, ACT_COL, TIME_COL] if col not in df.columns]
    if missing:
        print(f"Input event log is missing required column(s): {missing}")
        return None

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    df = df.dropna(subset=[CASE_COL, ACT_COL, TIME_COL])
    df = df.sort_values([CASE_COL, TIME_COL]).reset_index(drop=True)

    selected_cases = list(df[CASE_COL].drop_duplicates().head(MAX_CASES))
    sample = df[df[CASE_COL].isin(selected_cases)].copy()
    sample = sample.groupby(CASE_COL, sort=False).head(MAX_EVENTS_PER_CASE)
    sample = sample.head(MAX_EVENTS).copy()

    return sample


def add_safe_visual_activity_labels(sample: pd.DataFrame) -> pd.DataFrame:
    """
    Use short activity labels for Graphviz rendering only.
    Raw normalized log templates can contain punctuation that breaks DOT rendering
    in some Graphviz/PM4Py combinations. This does not affect thesis metrics.
    """
    sample = sample.copy()
    activities = list(sample[ACT_COL].drop_duplicates())
    mapping = {activity: f"A{idx:03d}" for idx, activity in enumerate(activities, start=1)}
    sample[ACT_COL] = sample[ACT_COL].map(mapping)
    print(f"Activity labels simplified for visualization: {len(mapping)} unique activities")
    return sample


def convert_to_pm4py_log(sample: pd.DataFrame):
    from pm4py.objects.conversion.log import converter as log_converter
    from pm4py.objects.log.util import dataframe_utils

    pm_df = sample.rename(
        columns={
            CASE_COL: "case:concept:name",
            ACT_COL: "concept:name",
            TIME_COL: "time:timestamp",
        }
    )
    pm_df = dataframe_utils.convert_timestamp_columns_in_df(pm_df)
    return log_converter.apply(pm_df, variant=log_converter.Variants.TO_EVENT_LOG)


def try_save_visualization(visualizer, visualization, output_path: Path) -> bool:
    try:
        if hasattr(visualization, "format"):
            visualization.format = output_path.suffix.lstrip(".")
        visualizer.save(visualization, str(output_path))
        print(f"Saved visualization: {output_path}")
        return True
    except Exception as exc:
        print(f"Could not save {output_path}: {type(exc).__name__}: {exc}")
        return False


def try_bpmn_visualization(pm4py_module, log) -> bool:
    try:
        from pm4py.visualization.bpmn import visualizer as bpmn_visualizer
    except ImportError as exc:
        print(f"BPMN visualizer is not available in this PM4Py installation: {type(exc).__name__}: {exc}")
        return False

    try:
        if hasattr(pm4py_module, "discover_bpmn_inductive"):
            print("Discovering BPMN model with PM4Py Inductive Miner...")
            bpmn_model = pm4py_module.discover_bpmn_inductive(log)
        elif hasattr(pm4py_module, "discover_process_tree_inductive") and hasattr(pm4py_module, "convert_to_bpmn"):
            print("Discovering process tree and converting it to BPMN...")
            process_tree = pm4py_module.discover_process_tree_inductive(log)
            bpmn_model = pm4py_module.convert_to_bpmn(process_tree)
        else:
            print("BPMN discovery/conversion is not available in this PM4Py installation.")
            return False

        print("Creating BPMN visualization...")
        visualization = bpmn_visualizer.apply(bpmn_model)
        BPMN_PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
        saved_png = try_save_visualization(bpmn_visualizer, visualization, BPMN_PNG_PATH)
        saved_svg = try_save_visualization(bpmn_visualizer, visualization, BPMN_SVG_PATH)

        if saved_png or saved_svg:
            print("BPMN visualization generated.")
            return True

        print("BPMN model was discovered, but no BPMN image could be saved.")
        return False
    except Exception as exc:
        print("BPMN visualization failed.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return False


def try_petri_visualization(pm4py_module, log) -> bool:
    try:
        from pm4py.visualization.petri_net import visualizer as pn_visualizer
    except ImportError as exc:
        print(f"Petri net visualizer is not available: {type(exc).__name__}: {exc}")
        return False

    try:
        print("Discovering Petri net fallback with Inductive Miner...")
        net, initial_marking, final_marking = pm4py_module.discover_petri_net_inductive(log)
        print("Creating Petri net fallback visualization...")
        visualization = pn_visualizer.apply(net, initial_marking, final_marking)
        PETRI_PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
        saved_png = try_save_visualization(pn_visualizer, visualization, PETRI_PNG_PATH)
        saved_svg = try_save_visualization(pn_visualizer, visualization, PETRI_SVG_PATH)

        if saved_png or saved_svg:
            print("BPMN unavailable, Petri net fallback generated.")
            return True

        print("Petri net fallback could not be saved.")
        return False
    except Exception as exc:
        print("Petri net fallback visualization failed.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return False


def main():
    print("Optional downstream process model visualization.")
    print("This image is a small-sample demonstration only.")
    print("It is not used for thesis metrics or result calculations.")

    try:
        import pm4py
    except ImportError as exc:
        print("Optional visualization dependencies are missing.")
        print("Install PM4Py visualization dependencies, including Graphviz, to create the process model image.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return

    try:
        sample = load_small_sample()
        if sample is None or sample.empty:
            print("No events available for optional process model visualization.")
            return

        cases_used = sample[CASE_COL].nunique()
        events_used = len(sample)
        print(f"Cases used for visualization: {cases_used}")
        print(f"Events used for visualization: {events_used}")
        print(f"Events per case capped at: {MAX_EVENTS_PER_CASE}")
        sample = add_safe_visual_activity_labels(sample)

        print("Converting sampled event log to PM4Py format...")
        log = convert_to_pm4py_log(sample)

        print("Trying BPMN visualization first.")
        bpmn_generated = try_bpmn_visualization(pm4py, log)
        if bpmn_generated:
            return

        print("BPMN unavailable, trying Petri net fallback.")
        petri_generated = try_petri_visualization(pm4py, log)
        if not petri_generated:
            print("Visualization could not be generated.")
            print("This often means Graphviz is not installed or not available on PATH.")
            print("Skipping optional visualization. Thesis result tables are unaffected.")
    except Exception as exc:
        print("Visualization failed and will be skipped.")
        print("This does not affect thesis metrics or result calculations.")
        print(f"Full error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
