using UnityEngine;
using uOSC;

public class HandReceiver : MonoBehaviour
{
    [Header("左手の2点")]
    public Transform leftWrist;
    public Transform leftIndexTip;

    [Header("右手の2点")]
    public Transform rightWrist;
    public Transform rightIndexTip;

    [Header("valid=0 のときにフェードするRenderer（左手）")]
    public Renderer[] leftRenderers;

    [Header("valid=0 のときにフェードするRenderer（右手）")]
    public Renderer[] rightRenderers;

    float _leftAlpha  = 0f;
    float _rightAlpha = 0f;
    bool  _leftValid  = false;
    bool  _rightValid = false;

    Vector3 _leftWristPos;
    Vector3 _leftIndexTipPos;
    Vector3 _rightWristPos;
    Vector3 _rightIndexTipPos;
    bool _leftDirty;
    bool _rightDirty;

    public bool LeftValid => _leftValid;
    public bool RightValid => _rightValid;
    public float LeftAlpha => _leftAlpha;
    public float RightAlpha => _rightAlpha;

    public Transform LeftWrist => leftWrist;
    public Transform LeftIndexTip => leftIndexTip;
    public Transform RightWrist => rightWrist;
    public Transform RightIndexTip => rightIndexTip;

    void Start()
    {
        var server = GetComponent<uOscServer>();
        server.onDataReceived.AddListener(OnDataReceived);
    }

    void OnDataReceived(Message message)
    {
        string addr = message.address;
        Debug.Log($"[HandReceiver] OSC {addr} values={message.values?.Length ?? 0}");

        if (TryApplyPointMessage(addr, message, "/box/hand/left/wrist", ref _leftWristPos, ref _leftValid))
        {
            _leftDirty = true;
            return;
        }
        if (TryApplyPointMessage(addr, message, "/box/hand/left/index_tip", ref _leftIndexTipPos, ref _leftValid))
        {
            _leftDirty = true;
            return;
        }
        if (TryApplyPointMessage(addr, message, "/box/hand/right/wrist", ref _rightWristPos, ref _rightValid))
        {
            _rightDirty = true;
            return;
        }
        if (TryApplyPointMessage(addr, message, "/box/hand/right/index_tip", ref _rightIndexTipPos, ref _rightValid))
        {
            _rightDirty = true;
        }
    }

    void ApplyPoints(Transform wrist, Transform indexTip, Vector3 wristPos, Vector3 indexTipPos)
    {
        if (wrist != null)
            wrist.localPosition = wristPos;
        if (indexTip != null)
            indexTip.localPosition = indexTipPos;
    }

    // TD は float で送るが uOSC が double に変換するケースがある
    static float ToFloat(object v) => v is float f ? f : (float)(double)v;

    static bool TryApplyPointMessage(string addr, Message message, string prefix, ref Vector3 point, ref bool valid)
    {
        if (!addr.StartsWith(prefix + "/") || message.values == null || message.values.Length < 1)
        {
            return false;
        }

        float value = ToFloat(message.values[0]);
        if (addr == prefix + "/x")
        {
            point.x = value;
            return true;
        }
        if (addr == prefix + "/y")
        {
            point.y = 1f - value;
            return true;
        }
        if (addr == prefix + "/z")
        {
            point.z = value * 0.1f;
            return true;
        }
        if (addr == prefix + "/valid")
        {
            valid = value >= 0.5f;
            return true;
        }

        return false;
    }

    void Update()
    {
        if (_leftDirty)
        {
            ApplyPoints(leftWrist, leftIndexTip, _leftWristPos, _leftIndexTipPos);
            _leftDirty = false;
        }
        if (_rightDirty)
        {
            ApplyPoints(rightWrist, rightIndexTip, _rightWristPos, _rightIndexTipPos);
            _rightDirty = false;
        }

        _leftAlpha  = Mathf.Lerp(_leftAlpha,  _leftValid  ? 1f : 0f, Time.deltaTime * 8f);
        _rightAlpha = Mathf.Lerp(_rightAlpha, _rightValid ? 1f : 0f, Time.deltaTime * 8f);
        SetAlpha(leftRenderers,  _leftAlpha);
        SetAlpha(rightRenderers, _rightAlpha);
    }

    void SetAlpha(Renderer[] renderers, float alpha)
    {
        if (renderers == null)
        {
            return;
        }

        foreach (var r in renderers)
        {
            if (r == null)
            {
                continue;
            }

            if (r.material.HasProperty("_BaseColor"))
            {
                var color = r.material.GetColor("_BaseColor");
                color.a = alpha;
                r.material.SetColor("_BaseColor", color);
                continue;
            }

            if (r.material.HasProperty("_Color"))
            {
                var color = r.material.color;
                color.a = alpha;
                r.material.color = color;
            }
        }
    }
}
