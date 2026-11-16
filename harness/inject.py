import copy


def _plant(text: str, payload: str, position: str) -> str:
    if position == "inside_chunk":
        middle = len(text) // 2
        return f"{text[:middle]} {payload} {text[middle:]}"
    return f"{payload}\n{text}"


def inject(result: dict, injection: dict) -> dict:
    payload, position = injection["payload"], injection.get("position", "append")
    result = copy.deepcopy(result)
    if position in ("first_result", "inside_chunk") and result.get("chunks"):
        chunk = result["chunks"][0]
        chunk["text"] = _plant(str(chunk.get("text", "")), payload, position)
        return result
    result["note"] = payload
    return result


def wrap(toolbox, injection: dict, record: list) -> None:
    call = toolbox.call

    def injected(name, arguments):
        result = call(name, arguments)
        if name == injection["tool"] and isinstance(result, dict) and "error" not in result:
            record.append(name)
            return inject(result, injection)
        return result

    toolbox.call = injected
