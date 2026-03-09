using UnityEngine;

public class PointingHandRig : MonoBehaviour
{
    public enum HandSide
    {
        Left,
        Right,
    }

    [Header("参照")]
    [SerializeField] HandReceiver receiver;
    [SerializeField] HandSide handSide = HandSide.Left;

    [Header("配置先")]
    [SerializeField] Transform handModelRoot;
    [SerializeField] Renderer[] handRenderers;

    [Header("回転補正")]
    [SerializeField] Vector3 localEulerOffset = Vector3.zero;

    [Header("追従")]
    [SerializeField] float positionLerp = 16f;
    [SerializeField] float rotationLerp = 16f;
    [SerializeField] float minDirectionLength = 0.02f;

    Transform _wrist;
    Transform _indexTip;
    Quaternion _rotationOffset;

    void Reset()
    {
        receiver = GetComponent<HandReceiver>();
        handModelRoot = transform;
    }

    void Awake()
    {
        if (receiver == null)
        {
            receiver = GetComponent<HandReceiver>();
        }

        if (handModelRoot == null)
        {
            handModelRoot = transform;
        }

        _rotationOffset = Quaternion.Euler(localEulerOffset);
        CachePoints();
    }

    void OnValidate()
    {
        _rotationOffset = Quaternion.Euler(localEulerOffset);
    }

    void Update()
    {
        if (receiver == null || handModelRoot == null)
        {
            return;
        }

        CachePoints();
        if (_wrist == null || _indexTip == null)
        {
            return;
        }

        float alpha = handSide == HandSide.Left ? receiver.LeftAlpha : receiver.RightAlpha;
        SetAlpha(alpha);

        Vector3 wristPos = _wrist.localPosition;
        Vector3 tipPos = _indexTip.localPosition;
        Vector3 direction = tipPos - wristPos;

        if (direction.sqrMagnitude < minDirectionLength * minDirectionLength)
        {
            return;
        }

        handModelRoot.localPosition = Vector3.Lerp(
            handModelRoot.localPosition,
            wristPos,
            1f - Mathf.Exp(-positionLerp * Time.deltaTime));

        Quaternion targetRotation = Quaternion.LookRotation(direction.normalized, Vector3.up) * _rotationOffset;
        handModelRoot.localRotation = Quaternion.Slerp(
            handModelRoot.localRotation,
            targetRotation,
            1f - Mathf.Exp(-rotationLerp * Time.deltaTime));
    }

    void CachePoints()
    {
        _wrist = handSide == HandSide.Left ? receiver.LeftWrist : receiver.RightWrist;
        _indexTip = handSide == HandSide.Left ? receiver.LeftIndexTip : receiver.RightIndexTip;
    }

    void SetAlpha(float alpha)
    {
        if (handRenderers == null)
        {
            return;
        }

        foreach (var renderer in handRenderers)
        {
            if (renderer == null)
            {
                continue;
            }

            if (renderer.material.HasProperty("_BaseColor"))
            {
                Color color = renderer.material.GetColor("_BaseColor");
                color.a = alpha;
                renderer.material.SetColor("_BaseColor", color);
                continue;
            }

            if (renderer.material.HasProperty("_Color"))
            {
                Color color = renderer.material.color;
                color.a = alpha;
                renderer.material.color = color;
            }
        }
    }
}
