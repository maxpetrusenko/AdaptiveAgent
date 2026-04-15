from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState
from app.agent.tools import calculator, current_time
from app.llm import build_chat_model

TOOLS = [calculator, current_time]


def create_agent(system_prompt: str | None = None):
    """Create a LangGraph agent with tools."""
    from app.agent.prompts import SYSTEM_PROMPT_V1

    prompt = system_prompt or SYSTEM_PROMPT_V1

    model = build_chat_model(purpose="agent", streaming=True).bind_tools(TOOLS)

    tool_node = ToolNode(TOOLS)

    def should_continue(state: AgentState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return END

    def call_model(state: AgentState) -> dict:
        messages = state["messages"]
        # Prepend system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt)] + messages
        response = model.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


async def run_agent(
    messages: list[dict],
    system_prompt: str | None = None,
) -> dict:
    """Run agent and return final response. Non-streaming."""
    agent = create_agent(system_prompt)

    # Convert dict messages to LangChain message objects
    lc_messages = []
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "system":
            lc_messages.append(SystemMessage(content=msg["content"]))

    result = await agent.ainvoke({"messages": lc_messages, "session_id": ""})

    # Extract final assistant message
    final_messages = result["messages"]
    assistant_content = ""
    tool_calls_data = []
    tool_results_data = []
    tool_names_by_id = {}

    for msg in final_messages:
        if isinstance(msg, AIMessage):
            if msg.content:
                assistant_content = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_id = tc.get("id", "")
                    tool_name = tc.get("name", "")
                    if tool_call_id and tool_name:
                        tool_names_by_id[tool_call_id] = tool_name
                    tool_calls_data.append(
                        {
                            "id": tool_call_id,
                            "name": tool_name,
                            "input": tc.get("args", {}),
                        }
                    )
        elif isinstance(msg, ToolMessage):
            tool_results_data.append(
                {
                    "id": msg.tool_call_id,
                    "name": tool_names_by_id.get(msg.tool_call_id, "unknown"),
                    "output": msg.content if isinstance(msg.content, str) else str(msg.content),
                }
            )

    return {
        "content": assistant_content,
        "tool_calls": tool_calls_data if tool_calls_data else None,
        "tool_results": tool_results_data if tool_results_data else None,
    }


async def stream_agent(
    messages: list[dict],
    system_prompt: str | None = None,
):
    """Stream agent responses as async generator of SSE events."""
    agent = create_agent(system_prompt)

    # Convert dict messages to LangChain message objects
    lc_messages = []
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "system":
            lc_messages.append(SystemMessage(content=msg["content"]))

    async for event in agent.astream_events(
        {"messages": lc_messages, "session_id": ""},
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                text = content if isinstance(content, str) else ""
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                if text:
                    yield {"type": "content", "content": text}

        elif kind == "on_tool_start":
            yield {
                "type": "tool_call",
                "name": event.get("name", "unknown"),
                "input": event.get("data", {}).get("input", {}),
            }

        elif kind == "on_tool_end":
            output = event.get("data", {}).get("output", "")
            if hasattr(output, "content"):
                output = output.content
            yield {
                "type": "tool_result",
                "name": event.get("name", "unknown"),
                "output": str(output)[:500],
            }

    yield {"type": "done"}
