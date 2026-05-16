import time
import json
import os

start_times = {}

def merge_json(base, update, parent_key=""):
    concat_fields = {"content", "reasoning", "reasoning_content", "text", "arguments"}
    
    if isinstance(base, dict) and isinstance(update, dict):
        for key, value in update.items():
            full_key = f"{parent_key}.{key}" if parent_key else key
            if key in base:
                base[key] = merge_json(base[key], value, full_key)
            else:
                base[key] = value
        return base
    elif isinstance(base, list) and isinstance(update, list):
        result = base.copy()
        for i, item in enumerate(update):
            if i < len(result):
                result[i] = merge_json(result[i], item, f"{parent_key}[{i}]")
            else:
                result.append(item)
        return result
    elif isinstance(update, str) and isinstance(base, str):
        field_name = parent_key.split(".")[-1] if parent_key else ""
        if field_name in concat_fields or parent_key.endswith(".content") or parent_key.endswith(".reasoning"):
            return base + update
        else:
            return update
    else:
        return update if update is not None else base

def log_debug(msg):
    try:
        with open("mitm_addon.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
            f.flush()
    except:
        pass

SESSIONS_FILE = None

def init():
    global SESSIONS_FILE
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(base, 'config')
        os.makedirs(config_dir, exist_ok=True)
        SESSIONS_FILE = os.path.join(config_dir, 'sessions.json')
        log_debug(f"Initialized SESSIONS_FILE: {SESSIONS_FILE}")
    except Exception as e:
        log_debug(f"Init config FAILED: {type(e).__name__}: {e}")

def get_session_number():
    if not SESSIONS_FILE or not os.path.exists(SESSIONS_FILE):
        return 1
    try:
        with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines = [l.strip() for l in lines if l.strip()]
            return len(lines) + 1
    except:
        return 1

init()

def request(flow):
    flow.metadata["start_time"] = time.time()
    log_debug(f"Request received: {flow.request.method} {flow.request.pretty_url}")

def response(flow):
    path = flow.request.path.lower()
    log_debug(f"Response received: {flow.request.method} {flow.request.pretty_url}")
    log_debug(f"Path: {path}")
    log_debug(f"Checking for patterns: v1/chat={('v1/chat' in path)}, chat/completions={('chat/completions' in path)}, anthropic={('anthropic' in path)}")
    
    if "v1/chat" in path or "chat/completions" in path or "anthropic" in path:
        log_debug("*** MATCHED AI API pattern! ***")
        
        url = flow.request.pretty_url
        req_body = flow.request.get_text() or ""
        resp_body = (flow.response.get_content().decode(errors='ignore') or "")
        
        log_debug(f"URL: {url}")
        log_debug(f"Request body length: {len(req_body)}")
        log_debug(f"Response body length: {len(resp_body)}")
        log_debug(f"Request body preview: {req_body[:200]}")
        log_debug(f"Response body preview: {resp_body[:200]}")

        duration = time.time() - flow.metadata["start_time"]
        log_debug(f"Duration: {duration:.3f}s")

        model_name = "unknown"
        user_msg = ""
        ai_msg = ""
        reasoning = ""
        function_call = None
        tool_calls = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        is_stream = False

        try:
            req_j = json.loads(req_body)
            model_name = req_j.get("model", "unknown")
            log_debug(f"Model: {model_name}")

            if "messages" in req_j:
                msgs = req_j["messages"]
                log_debug(f"Number of messages: {len(msgs)}")
                for msg in msgs:
                    if msg.get("role") == "user":
                        user_msg = msg.get("content", "")
                if msgs:
                    user_msg = msgs[-1].get("content", user_msg)
            elif "prompt" in req_j:
                user_msg = req_j.get("prompt", {}).get("text", "")
            log_debug(f"User message length: {len(user_msg)}")

            if "data: " in resp_body:
                log_debug("Detected STREAMING response")
                is_stream = True
                first_token_time = None

                merged_response = {}

                for line in resp_body.split("\n"):
                    if line.startswith("data: ") and "[DONE]" not in line:
                        try:
                            if not first_token_time:
                                first_token_time = time.time()
                            chunk_data = json.loads(line[6:])
                            merged_response = merge_json(merged_response, chunk_data)
                        except Exception as e:
                            log_debug(f"Error parsing chunk: {e}")
                            pass

                ai_msg = ""
                reasoning = ""
                function_call = None
                tool_calls = None
                
                if "choices" in merged_response and merged_response["choices"]:
                    choice = merged_response["choices"][0]
                    if "message" in choice:
                        ai_msg = choice["message"].get("content", "")
                        function_call = choice["message"].get("function_call")
                        tool_calls = choice["message"].get("tool_calls")
                        reasoning = choice["message"].get("reasoning", "") or choice["message"].get("reasoning_content", "")
                    elif "delta" in choice:
                        ai_msg = choice["delta"].get("content", "")
                        function_call = choice["delta"].get("function_call")
                        tool_calls = choice["delta"].get("tool_calls")
                        reasoning = choice["delta"].get("reasoning", "") or choice["delta"].get("reasoning_content", "")
                
                if not reasoning:
                    reasoning = merged_response.get("reasoning", "") or merged_response.get("reasoning_content", "")
                
                if "usage" in merged_response:
                    usage = merged_response["usage"]
                
                ttft = (first_token_time - flow.metadata["start_time"]) if first_token_time else duration
                log_debug(f"TTFT (streaming): {ttft:.3f}s")
                log_debug(f"AI content length (streaming): {len(ai_msg)}")
                log_debug(f"Reasoning content length (streaming): {len(reasoning)}")
            else:
                log_debug("Detected NON-STREAMING response")
                try:
                    res_j = json.loads(resp_body)

                    if "choices" in res_j:
                        choice = res_j["choices"][0]
                        message = choice.get("message", {})
                        ai_msg = message.get("content", "")
                        
                        if "function_call" in message:
                            function_call = message["function_call"]
                        if "tool_calls" in message:
                            tool_calls = message["tool_calls"]
                        if "reasoning" in message:
                            reasoning = message["reasoning"]
                        if "reasoning_content" in message:
                            reasoning = message["reasoning_content"]
                    elif "content" in res_j:
                        ai_msg = res_j["content"][0].get("text", "") if isinstance(res_j["content"], list) else res_j.get("text", "")
                        
                        if "reasoning" in res_j:
                            reasoning = res_j["reasoning"]
                        if "reasoning_content" in res_j:
                            reasoning = res_j["reasoning_content"]
                        if "function_call" in res_j:
                            function_call = res_j["function_call"]
                        if "tool_calls" in res_j:
                            tool_calls = res_j["tool_calls"]

                    if "usage" in res_j:
                        usage = res_j["usage"]
                    elif "metrics" in res_j:
                        usage = {"prompt_tokens": res_j["metrics"].get("tokens_prompt", 0),
                                 "completion_tokens": res_j["metrics"].get("tokens_completion", 0),
                                 "total_tokens": res_j["metrics"].get("tokens_total", 0)}

                    ttft = duration
                except Exception as e:
                    log_debug(f"Error parsing non-stream response: {e}")
                    ai_msg = resp_body[:500]
                    ttft = duration

            log_debug(f"AI response length: {len(ai_msg)}")
            log_debug(f"Usage: {usage}")

            if usage["total_tokens"] == 0:
                log_debug("Estimating tokens since API didn't provide usage")
                usage["prompt_tokens"] = len(req_body) // 4
                usage["completion_tokens"] = len(ai_msg) // 4
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

            tps = round(usage["completion_tokens"] / duration, 2) if duration > 0 else 0

            session = {
                "id": f"{int(time.time()*1000)}",
                "url": url,
                "model": model_name,
                "user": user_msg,
                "ai": ai_msg,
                "reasoning": reasoning,
                "function_call": function_call,
                "tool_calls": tool_calls,
                "ttft": f"{round(ttft, 3)}s",
                "duration": f"{round(duration, 2)}s",
                "tokens": usage,
                "speed": f"{tps} t/s",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stream": is_stream
            }

            log_debug(f"Session ready to save: model={model_name}, user_len={len(user_msg)}, ai_len={len(ai_msg)}")

            session_num = get_session_number()
            
            if SESSIONS_FILE:
                try:
                    with open(SESSIONS_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(session, ensure_ascii=False) + "\n")
                    log_debug(f"Session {session_num} saved to {SESSIONS_FILE}")
                except Exception as e:
                    log_debug(f"FAILED to save session: {type(e).__name__}: {e}")
            else:
                log_debug("SESSIONS_FILE is None, cannot save!")

            try:
                config_dir = os.path.dirname(SESSIONS_FILE) if SESSIONS_FILE else '.'
                req_path = os.path.join(config_dir, f"{session_num}-req.json")
                with open(req_path, "w", encoding="utf-8") as f:
                    if req_body:
                        try:
                            req_j = json.loads(req_body)
                            json.dump(req_j, f, ensure_ascii=False, indent=2)
                        except:
                            f.write(req_body)
                    log_debug(f"Request saved to {req_path}")
            except Exception as e:
                log_debug(f"FAILED to save req.json: {type(e).__name__}: {e}")

            try:
                config_dir = os.path.dirname(SESSIONS_FILE) if SESSIONS_FILE else '.'
                resp_path = os.path.join(config_dir, f"{session_num}-resp.json")
                
                if is_stream:
                    resp_json = merged_response.copy()
                    if "choices" in resp_json and resp_json["choices"]:
                        choice = resp_json["choices"][0]
                        if "delta" in choice:
                            choice["message"] = choice.pop("delta")
                            choice["message"]["role"] = "assistant"
                            choice["finish_reason"] = "stop"
                    resp_json["stream"] = True
                else:
                    try:
                        resp_json = json.loads(resp_body)
                    except:
                        resp_json = {"raw": resp_body}
                
                with open(resp_path, "w", encoding="utf-8") as f:
                    json.dump(resp_json, f, ensure_ascii=False, indent=2)
                log_debug(f"Response saved to {resp_path} (streaming={is_stream})")
            except Exception as e:
                log_debug(f"FAILED to save resp.json: {type(e).__name__}: {e}")

        except Exception as e:
            log_debug(f"*** MAIN PARSE ERROR: {type(e).__name__}: {e}")
            log_debug(f"req_body: {req_body[:500]}")
            log_debug(f"resp_body: {resp_body[:500]}")
    else:
        log_debug("Not an AI API request, skipping")
