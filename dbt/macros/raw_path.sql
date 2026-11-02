{% macro quarter_start(q) -%}
  {#- '2026Q4' -> DATE '2026-10-01' -#}
  make_date(cast(left({{ q }}, 4) as int), (cast(right({{ q }}, 1) as int) - 1) * 3 + 1, 1)
{%- endmacro %}

{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
