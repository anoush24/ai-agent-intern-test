order_lookup_tool = {
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": (
            "Look up the current status of a customer order by order ID. "
            "Returns only customer-safe fields (status, carrier, tracking, "
            "estimated delivery, items) - never email, address, or internal "
            "notes, because those are never present in the underlying data "
            "this tool can access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID as given by the customer, e.g. ORD-1007",
                }
            },
            "required": ["order_id"],
        },
    },
}

TOOLS = [order_lookup_tool]