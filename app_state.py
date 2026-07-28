def apply_options_transactionally(options, get_option, set_option):
    """Apply config options and best-effort restore prior values on failure."""
    previous_values = {}
    applied_options = []

    try:
        for option, value in options.items():
            previous_values[option] = get_option(option)
            applied_options.append(option)
            set_option(option, value)
    except Exception:
        for option in reversed(applied_options):
            try:
                set_option(option, previous_values[option])
            except Exception:
                pass
        raise


def switch_theme(session_state, apply_theme):
    """Switch session theme, falling back to CSS when native sync fails."""
    new_theme = "light" if session_state.get("ui_theme") == "dark" else "dark"

    try:
        apply_theme(new_theme)
    except Exception as exc:
        session_state["theme_native_sync_error"] = str(exc)
    else:
        session_state.pop("theme_native_sync_error", None)

    session_state["ui_theme"] = new_theme
    session_state["theme_live_override"] = True
    return new_theme


def persist_analysis_record(session_state, record, save_history, max_items):
    """Persist a new record before committing it to the current session."""
    history = list(session_state.get("analysis_history", []))
    new_history = (history + [record])[-max_items:]

    save_history(new_history)

    session_state["analysis_history"] = new_history
    session_state["just_analyzed"] = True
    return new_history
