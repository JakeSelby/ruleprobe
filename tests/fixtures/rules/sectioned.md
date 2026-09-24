# Example project rules

## Testing

Run the suite before saying a change works.

## Example session

```sh
# Not a heading: this line sits inside a fenced block.
python3 -m unittest discover -s tests
```

## Dependencies

Install with `uv`, never with `sudo pip`.

```sh
uv pip install example-package
```

### Pinning

- Pin every development tool to an exact version.
