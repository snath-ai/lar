# FunctionalNode & @node

The `FunctionalNode` is a lightweight primitive designed for pure-python data transformation, formatting, or validation *that does not require an LLM* or an external tool. It is effectively a Python function wrapped into a graph primitive.

While you could use a `ToolNode` to execute pure functions, `FunctionalNode` is optimized for direct manipulation of the `GraphState` and provides a beautiful `@node` decorator syntax for rapid development.

## The `@node` Decorator

The recommended way to create a FunctionalNode is using the `@node` decorator syntax. 

```python
from lar import node, GraphState

@node(output_key="topic_normalised")
def normalise_topic(state: GraphState) -> str:
    """
    Strips whitespace and title-cases the research topic from state.
    """
    raw = state.get("topic") or ""
    return raw.strip().title()

# To slot it into the graph, wire the `.next_node` attribute:
normalise_topic.next_node = some_other_node
```

## How It Works

Under the hood, the `@node` decorator intercepts the python function and instantiates a `FunctionalNode` object. When the `GraphExecutor` hits this node, it simply passes the entire `GraphState` dictionary to the function, executes the logic, takes the return value, and saves it into the state under the defined `output_key`.

> [!WARNING]
> Because the decorator instantiates the node *at definition time*, you cannot pass `next_node` as an argument to the decorator. You must wire `my_func.next_node = next_step` after the function is defined, which naturally compliments Lár's reverse-definition graph paradigm.

## Manual Instantiation

If you prefer not to use decorators, you can instantiate it directly (though `ToolNode` is generally preferred for explicit input mapping):

```python
from lar import FunctionalNode

def my_transform(state):
    return state.get("x", 0) + 1

math_node = FunctionalNode(
    func=my_transform,
    output_key="x_plus_one",
    next_node=end_node
)
```

## Parameters

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `func` | `Callable` | Required | A python function that accepts `state` (dict) and returns a string, dictionary, or primitive. |
| `output_key` | `str` | Required | Where in the `GraphState` the function's return value will be assigned. |
| `next_node` | `Node` | `None` | The next node to transition to. |
