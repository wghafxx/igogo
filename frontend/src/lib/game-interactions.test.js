import { preventGameDrag } from "./game-interactions";

const createEvent = (target) => {
  const event = {
    target,
    defaultPrevented: false,
    preventDefault: jest.fn(function prevent() {
      event.defaultPrevented = true;
    }),
  };
  return event;
};

describe("preventGameDrag", () => {
  test("prevents drag on non-input game elements", () => {
    document.body.innerHTML = '<div id="card"><span id="text">Skin name</span></div>';
    const text = document.getElementById("text");
    const event = createEvent(text);

    preventGameDrag(event);

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  test.each([
    '<input id="allowed" value="abc" />',
    '<textarea id="allowed">abc</textarea>',
    '<div contenteditable="true" id="allowed">editable</div>',
  ])("does not prevent drag in editable controls: %s", (markup) => {
    document.body.innerHTML = markup;
    const allowed = document.getElementById("allowed");
    const event = createEvent(allowed);

    preventGameDrag(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});
