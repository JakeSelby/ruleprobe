Each section below states one rule in the shape of one shipped catalog entry, in catalog
order. Text above the first heading is no rule, so this paragraph binds nothing.

## Testing

Run the tests before you say a change works.

## Hooks

Never skip the pre-commit hooks. Fix what a failing hook found.

## Pushing

Never force-push to `main`.

## Dependencies

Use `uv`, not `pip`, for every install.

## Reading files

Do not read a whole file into context. Read the range you need.

## Commits

Use Conventional Commits for every commit subject.

## Secrets

- Never commit a `.env` file or a private key.
