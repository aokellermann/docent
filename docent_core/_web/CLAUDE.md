# Frontend Style Guide

## Spacing

- **Prefer `space-y-*` over individual margins**: When vertically stacking elements, use Tailwind's `space-y-*` utility on the parent container instead of adding `mt-*` or `mb-*` margins to each child element.

  ```tsx
  // ✅ Good
  <div className="space-y-4">
    <Component />
    <Component />
    <Component />
  </div>

  // ❌ Avoid
  <div>
    <Component className="mb-4" />
    <Component className="mb-4" />
    <Component />
  </div>
  ```

- Similarly, use `space-x-*` for horizontal spacing instead of `ml-*` or `mr-*` on children.

- This keeps spacing logic centralized in the parent, making it easier to adjust and maintain consistent gaps.

- **Default spacing convention**: Containers should use `p-3` for outer padding, with `space-y-2` between groups of elements inside.

  ```tsx
  <div className="p-3 space-y-2">
    <GroupA />
    <GroupB />
    <GroupC />
  </div>
  ```

## React Patterns

- **Avoid `useEffect` when possible**: `useEffect` is often overused. Prefer these alternatives:

  - **Derived/computed values**: If something can be calculated from props or state, compute it during render instead of syncing it with an effect.

    ```tsx
    // ✅ Good - derive during render
    const fullName = `${firstName} ${lastName}`;

    // ❌ Avoid - unnecessary effect
    const [fullName, setFullName] = useState('');
    useEffect(() => {
      setFullName(`${firstName} ${lastName}`);
    }, [firstName, lastName]);
    ```

  - **Event handlers**: If something should happen in response to a user action, put it in the event handler, not an effect.

    ```tsx
    // ✅ Good - handle in event
    const handleSubmit = () => {
      saveData();
      showToast('Saved!');
    };

    // ❌ Avoid - effect reacting to state change
    useEffect(() => {
      if (submitted) showToast('Saved!');
    }, [submitted]);
    ```

  - **`useMemo`**: For expensive calculations that depend on props/state.

  - **`key` prop**: To reset component state when an ID changes, use `key={id}` instead of an effect that resets state.

  - **Refs**: For DOM interactions like focus, scroll, or measurements, use ref callbacks instead of effects.

    ```tsx
    // ✅ Good - ref callback
    <input ref={(el) => el?.focus()} />

    // ❌ Avoid - effect for DOM interaction
    const inputRef = useRef(null);
    useEffect(() => {
      inputRef.current?.focus();
    }, []);
    ```
